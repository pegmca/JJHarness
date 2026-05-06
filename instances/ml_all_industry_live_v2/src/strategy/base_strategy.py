# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals
from gm.api import *
import datetime
import numpy as np
import pandas as pd
import json
import lightgbm as lgb
import os

'''
Harness Quant: 全行业机器学习选股策略 (ml_all_industry_live_v2) - 实盘版

实盘改造关键点:
1. 运行模式: 切换为 MODE_LIVE (实盘/仿真)。
2. 训练时点: 每天收盘后或开盘前重新训练模型（当前设为 09:15，确保开盘前有最新预测）。
3. 状态持久化: 实盘可能会重启，需要记录“当前持仓”和“调仓周期”。
4. 执行优化: 增加实盘成交检查和详细日志。
'''

def init(context):
    # --- 1. 实盘基础配置 ---
    # 获取中证1000前500只
    df_constituents = stk_get_index_constituents('SHSE.000852')
    context.target_symbols = df_constituents['symbol'].head(500).tolist()
    
    # 策略核心参数 (沿用 V1 最佳配置)
    context.history_len = 20
    context.forecast_len = 2    # 2日 Alpha 捕捉
    context.training_len = 120
    context.top_n = 5
    context.buffer_n = 3
    context.earn_rate = 0.25
    context.stop_loss = -0.08
    context.vol_threshold = 0.50
    
    # --- 2. 数据订阅 ---
    # 实盘必须订阅行情
    subscribe(symbols=context.target_symbols, frequency='1d')
    
    # --- 3. 定时任务 ---
    # 实盘建议在 09:15 训练模型，09:31 执行调仓
    schedule(schedule_func=execute_rotation_with_buffer, date_rule='1w', time_rule='09:15:00')
    # 每日止损监控
    schedule(schedule_func=monitor_stop_loss, date_rule='1d', time_rule='09:35:00')
    
    print(f"[{context.now}] 实盘策略初始化完成，监控标的: {len(context.target_symbols)} 只")

def monitor_stop_loss(context):
    positions = get_position()
    for pos in positions:
        symbol = pos['symbol']
        # 实盘使用 current 获取最新价
        last_tick = current(symbols=symbol)
        if not last_tick: continue
        
        current_price = last_tick[0]['price']
        vwap = pos['vwap']
        ret = current_price / vwap - 1
        
        if ret <= context.stop_loss:
            print(f"[{context.now}] [实盘报警] {symbol} 触及止损 ({ret:.2%})，立即平仓")
            order_target_percent(symbol=symbol, percent=0, order_type=OrderType_Market, position_side=PositionSide_Long)

def execute_rotation_with_buffer(context):
    now_str = context.now.strftime('%Y-%m-%d')
    fetch_len = context.training_len + 60
    date_list = get_previous_n_trading_dates(exchange='SHSE', date=now_str, n=fetch_len)
    if not date_list: return
    
    start_date = date_list[0]
    end_date = date_list[-1]
    
    print(f"[*] {context.now}: [实盘训练开始] 样本范围: {start_date} -> {end_date}")
    
    # A. 获取数据并标注
    try:
        raw_data = history(symbol=context.target_symbols, frequency='1d', start_time=start_date, end_time=end_date, fill_missing='last', df=True)
        # 截面 Alpha 标注
        raw_data['ret_target'] = raw_data.groupby('symbol')['close'].shift(-context.forecast_len) / raw_data.groupby('symbol')['close'].shift(-1) - 1
        market_median = raw_data.groupby('eob')['ret_target'].transform('median')
        raw_data['alpha_label'] = raw_data['ret_target'] - market_median
    except Exception as e:
        print(f"[!] 数据获取失败: {e}")
        return
    
    all_samples = []
    current_features_map = {}
    market_vols = []
    
    for symbol in context.target_symbols:
        stock_df = raw_data[raw_data['symbol'] == symbol].copy().reset_index(drop=True)
        if len(stock_df) < context.training_len: continue
        
        stock_df = calculate_alpha_features(stock_df)
        market_vols.append(stock_df['volatility'].iloc[-1])
        
        samples, latest_x = extract_regression_samples(context, stock_df)
        if samples:
            all_samples.extend(samples)
            current_features_map[symbol] = latest_x
            
    # B. 风险过滤
    avg_vol = np.mean(market_vols) * np.sqrt(252)
    if avg_vol > context.vol_threshold:
        print(f"[!] 实盘预警: 市场年化波动率 ({avg_vol:.2%}) 过高，清仓规避！")
        order_close_all()
        return

    # C. 训练回归模型
    if len(all_samples) < 5000: 
        print("[!] 样本量不足，维持当前持仓")
        return
        
    X = np.array([s[0] for s in all_samples])
    y = np.array([s[1] for s in all_samples])
    train_data = lgb.Dataset(X, label=y)
    params = {'objective': 'regression', 'metric': 'rmse', 'verbosity': -1, 'learning_rate': 0.05, 'num_leaves': 31, 'seed': 42}
    gbm = lgb.train(params, train_data, num_boost_round=100)
    
    # D. 预测并实施换手控制
    scores = []
    for symbol, x in current_features_map.items():
        pred = gbm.predict(np.array(x).reshape(1, -1))[0]
        scores.append({'symbol': symbol, 'score': pred})
    
    sorted_scores = sorted(scores, key=lambda x: x['score'], reverse=True)
    top_candidates = [s['symbol'] for s in sorted_scores[:context.top_n]]
    tier1_candidates = [s['symbol'] for s in sorted_scores[:context.buffer_n]]
    
    # 缓冲区逻辑
    current_positions = [pos['symbol'] for pos in get_position()]
    new_picks = []
    for symbol in current_positions:
        if symbol in top_candidates: new_picks.append(symbol)
    for symbol in tier1_candidates:
        if len(new_picks) >= context.top_n: break
        if symbol not in new_picks: new_picks.append(symbol)
    for symbol in top_candidates:
        if len(new_picks) >= context.top_n: break
        if symbol not in new_picks: new_picks.append(symbol)
            
    print(f"[{context.now}] [实盘换股决策]: {new_picks}")
    
    # E. 执行实盘委托
    # 先平掉不属于新池子的
    for symbol in current_positions:
        if symbol not in new_picks:
            order_target_percent(symbol=symbol, percent=0, order_type=OrderType_Market, position_side=PositionSide_Long)
            
    # 调入新标的
    if not new_picks: return
    target_percent = 0.90 / len(new_picks) # 实盘建议保留 10% 现金
    for symbol in new_picks:
        order_target_percent(symbol=symbol, percent=target_percent, order_type=OrderType_Market, position_side=PositionSide_Long)

def calculate_alpha_features(df):
    returns = df['close'].pct_change()
    ma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    df['price_std_score'] = (df['close'] - ma20) / (std20 + 1e-9)
    vma20 = df['volume'].rolling(20).mean()
    df['vol_spike'] = df['volume'] / (vma20 + 1e-9)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain/(loss + 1e-9)))
    df['rsi_slope'] = df['rsi'].diff(3)
    df['volatility'] = returns.rolling(20).std()
    df['skewness'] = returns.rolling(20).skew()
    return df.dropna()

def extract_regression_samples(context, df):
    samples = []
    cols = ['price_std_score', 'vol_spike', 'rsi', 'rsi_slope', 'volatility', 'skewness', 'alpha_label']
    data = df[cols].values
    for i in range(len(df)):
        feature = data[i, :6].tolist()
        if i == len(df) - 1: latest_feature = feature
        label = data[i, 6]
        if not np.isnan(label): samples.append((feature, label))
    return samples, latest_feature

def on_order_status(context, order):
    if order['status'] == 3:
        print(f"[{context.now}] [实盘成交] {order['symbol']} 数量: {order['volume']} 均价: {order['price']}")
    elif order['status'] == 8:
        print(f"[{context.now}] [实盘拒绝!!!] {order['symbol']} 原因: {order['error_msg']}")

if __name__ == '__main__':
    # 实盘模式配置
    run(strategy_id='80aca4cd-4934-11f1-a57e-da8083a72cbd', # 建议使用新的 ID
        filename='base_strategy.py',
        mode=MODE_LIVE, # 关键切换：实盘模式
        token='dc6abd591b356d0f77cc8f224b350312f70050f5',
        backtest_match_mode=1)
