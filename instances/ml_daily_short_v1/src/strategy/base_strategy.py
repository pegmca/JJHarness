# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals
from gm.api import *
import datetime
import numpy as np
import pandas as pd
import json
import lightgbm as lgb

'''
Harness Quant: 每日调仓机器学习短线策略 (ml_daily_short_v1)

策略逻辑:
1. 预测周期: forecast_len=1。针对每日调仓，预测下一日的超额收益。
2. 机器学习模型: LightGBM 回归模型，捕捉截面相对收益。
3. 换手控制 (Position Buffer): 
   - 维持 Top 5 持仓。
   - 只有当新股票的预测值进入前 3 名时，才替换原有持仓，平衡灵敏度与交易成本。
4. 风控: 
   - 5% 个股硬止损。
   - 市场波动率过滤 (年化波动率 > 50% 时清仓)。
'''

def init(context):
    # 选股池: 中证1000成份股 (前500只)
    df_constituents = stk_get_index_constituents('SHSE.000852')
    context.target_symbols = df_constituents['symbol'].head(500).tolist()
    
    # 策略参数
    context.history_len = 20
    context.forecast_len = 1    # 针对每日调仓，预测 1 日收益
    context.training_len = 120  # 训练窗口
    context.top_n = 5           # 持仓数量
    context.buffer_n = 3        # 换仓缓冲阈值 (进入前3才替换)
    context.stop_loss = -0.05   # 个股硬止损 (短线更敏锐)
    context.vol_threshold = 0.50 # 市场波动率阈值
    
    # 订阅分钟线用于止损监控
    subscribe(symbols=context.target_symbols, frequency='60s')
    # 每天 09:31 执行调仓逻辑
    schedule(schedule_func=algo, date_rule='1d', time_rule='09:31:00')

def on_bar(context, bars):
    # 分钟级实时止损监控
    current_positions = {pos['symbol']: pos for pos in get_position()}
    if not current_positions:
        return

    for bar in bars:
        if bar.symbol in current_positions:
            pos = current_positions[bar.symbol]
            # 计算当前收益率
            ret = bar.close / pos['vwap'] - 1
            if ret <= context.stop_loss:
                order_target_percent(symbol=bar.symbol, percent=0, order_type=OrderType_Market, position_side=PositionSide_Long)
                print(f"{context.now}: 标的 {bar.symbol} 触发分钟级实时止损 ({ret:.2%})")

def algo(context):
    # 每日执行调仓逻辑
    execute_rotation_with_buffer(context)

def execute_rotation_with_buffer(context):
    now_str = context.now.strftime('%Y-%m-%d')
    fetch_len = context.training_len + 60
    # 获取交易日历
    date_list = get_previous_n_trading_dates(exchange='SHSE', date=now_str, n=fetch_len)
    if not date_list: return
    
    start_date = date_list[0]
    end_date = date_list[-1]
    
    print(f"[*] {context.now}: 启动每日 ML 短线回归训练...")
    
    # 获取历史日线数据
    raw_data = history(symbol=context.target_symbols, frequency='1d', start_time=start_date, end_time=end_date, fill_missing='last', df=True)
    if raw_data.empty: return

    # 计算目标值: 未来 forecast_len 日的收益率 - 市场中位数收益率
    raw_data['ret_target'] = raw_data.groupby('symbol')['close'].shift(-context.forecast_len) / raw_data.groupby('symbol')['close'].shift(-1) - 1
    market_median = raw_data.groupby('eob')['ret_target'].transform('median')
    raw_data['alpha_label'] = raw_data['ret_target'] - market_median
    
    all_samples = []
    current_features_map = {}
    market_vols = []
    
    for symbol in context.target_symbols:
        stock_df = raw_data[raw_data['symbol'] == symbol].copy().reset_index(drop=True)
        if len(stock_df) < context.training_len: continue
        
        # 特征工程
        stock_df = calculate_alpha_features(stock_df)
        if stock_df.empty: continue
        
        market_vols.append(stock_df['volatility'].iloc[-1])
        
        # 提取训练样本和最新特征
        samples, latest_x = extract_regression_samples(context, stock_df)
        if samples:
            all_samples.extend(samples)
            current_features_map[symbol] = latest_x
            
    # 风险过滤: 市场年化波动率过高则空仓
    if market_vols and np.mean(market_vols) * np.sqrt(252) > context.vol_threshold:
        print("[!] 市场波动率过高，全线清仓待机")
        order_close_all()
        return

    # 训练模型 (LightGBM)
    if len(all_samples) < 3000: # 样本量要求略低于周频，因为我们更注重近期
        print(f"[!] 样本不足 ({len(all_samples)})，跳过本次调仓")
        return
        
    X = np.array([s[0] for s in all_samples])
    y = np.array([s[1] for s in all_samples])
    train_data = lgb.Dataset(X, label=y)
    params = {
        'objective': 'regression',
        'metric': 'rmse',
        'verbosity': -1,
        'learning_rate': 0.08, # 稍微提高学习率以捕捉短线波动
        'num_leaves': 31,
        'seed': 42
    }
    gbm = lgb.train(params, train_data, num_boost_round=100)
    
    # 预测下一日评分
    scores = []
    for symbol, x in current_features_map.items():
        pred = gbm.predict(np.array(x).reshape(1, -1))[0]
        scores.append({'symbol': symbol, 'score': pred})
    
    # 按预测分数降序排列
    sorted_scores = sorted(scores, key=lambda x: x['score'], reverse=True)
    top_candidates = [s['symbol'] for s in sorted_scores[:context.top_n]]
    tier1_candidates = [s['symbol'] for s in sorted_scores[:context.buffer_n]]
    
    # --- 换手控制逻辑 ---
    current_positions = [pos['symbol'] for pos in get_position()]
    new_picks = []
    
    # 1. 优先保留仍在 Top 5 中的老股票 (惯性)
    for symbol in current_positions:
        if symbol in top_candidates:
            new_picks.append(symbol)
            
    # 2. 只有新标的进入 Tier 1 (前3) 时才替换老标的，以降低每日调仓的磨损
    for symbol in tier1_candidates:
        if len(new_picks) >= context.top_n: break
        if symbol not in new_picks:
            new_picks.append(symbol)
            
    # 3. 如果还没满，才按顺序补齐
    for symbol in top_candidates:
        if len(new_picks) >= context.top_n: break
        if symbol not in new_picks:
            new_picks.append(symbol)
            
    print(f"[*] {context.now}: 最终调仓决策 (Daily Buffer): {new_picks}")
    
    # 卖出不在新名单中的股票
    for symbol in current_positions:
        if symbol not in new_picks:
            order_target_percent(symbol=symbol, percent=0, order_type=OrderType_Market, position_side=PositionSide_Long)
            
    # 买入/调整仓位
    target_percent = 0.95 / len(new_picks) if new_picks else 0
    for symbol in new_picks:
        order_target_percent(symbol=symbol, percent=target_percent, order_type=OrderType_Market, position_side=PositionSide_Long)

def calculate_alpha_features(df):
    """计算短线 Alpha 特征"""
    returns = df['close'].pct_change()
    # 1. 价格对 20 日均线的乖离度 (Z-Score)
    ma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    df['price_std_score'] = (df['close'] - ma20) / (std20 + 1e-9)
    # 2. 成交量突变 (Volume Spike)
    vma20 = df['volume'].rolling(20).mean()
    df['vol_spike'] = df['volume'] / (vma20 + 1e-9)
    # 3. RSI 动量加速度 (RSI Slope)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain/(loss + 1e-9)))
    df['rsi_slope'] = df['rsi'].diff(3)
    # 4. 收益率偏度 (Skewness)
    df['skewness'] = returns.rolling(20).skew()
    # 5. 波动率
    df['volatility'] = returns.rolling(20).std()
    
    return df.dropna()

def extract_regression_samples(context, df):
    """提取训练样本"""
    samples = []
    # 特征列
    cols = ['price_std_score', 'vol_spike', 'rsi', 'rsi_slope', 'volatility', 'skewness', 'alpha_label']
    data = df[cols].values
    for i in range(len(df)):
        feature = data[i, :6].tolist()
        if i == len(df) - 1: 
            latest_feature = feature
        label = data[i, 6]
        if not np.isnan(label): 
            samples.append((feature, label))
    return samples, latest_feature

def on_backtest_finished(context, indicator):
    print('*'*50)
    result = {
        "pnl_ratio": indicator.pnl_ratio * 100, 
        "sharpe_ratio": indicator.sharp_ratio, 
        "max_drawdown": indicator.max_drawdown * 100, 
        "win_rate": indicator.win_ratio * 100
    }
    print('BACKTEST_RESULT_JSON: {}'.format(json.dumps(result)))

if __name__ == '__main__':
    run(strategy_id='507c001e-49e4-11f1-a872-da8083a72cab', # 请填写策略 ID
        filename='base_strategy.py', 
        mode=MODE_BACKTEST, 
        token='dc6abd591b356d0f77cc8f224b350312f70050f5', 
        backtest_start_time='2025-11-10 09:00:00', 
        backtest_end_time='2026-05-06 16:00:00', 
        backtest_adjust=ADJUST_PREV, 
        backtest_initial_cash=50000, 
        backtest_commission_ratio=0.0003, 
        backtest_slippage_ratio=0.0001, 
        backtest_match_mode=1)
