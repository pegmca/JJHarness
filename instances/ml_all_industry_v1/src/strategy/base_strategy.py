# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals
from gm.api import *
import datetime
import numpy as np
import pandas as pd
import json
import lightgbm as lgb

'''
Harness Quant: 全行业机器学习选股策略 (ml_all_industry_v1) - 换手控制版

深度优化目标: 解决“赚了指数不赚钱”的问题
1. 预测周期缩短: forecast_len=2。中证1000爆发力快，预测2日收益能更早捕捉起涨点。
2. 换手控制 (Position Buffer): 
   - 维持 Top 5 持仓。
   - 只有当新股票的预测值排名前 3 时，才允许替换掉旧股票。
   - 这种“惯性”机制能显著降低摩擦成本。
3. 止损保护: 增加 8% 个股硬止损，防止小盘股极端杀跌。
'''

def init(context):
    df_constituents = stk_get_index_constituents('SHSE.000852')
    context.target_symbols = df_constituents['symbol'].head(500).tolist()
    
    context.history_len = 20
    context.forecast_len = 2    # 缩短预测窗口，捕捉更敏锐的爆发力
    context.training_len = 120
    context.top_n = 5
    context.buffer_n = 3        # 只有进前3才换股
    context.earn_rate = 0.25
    context.stop_loss = -0.08   # 硬止损
    context.vol_threshold = 0.50
    
    subscribe(symbols=context.target_symbols, frequency='1d')
    schedule(schedule_func=algo, date_rule='1w', time_rule='09:31:00')

def algo(context):
    # 每天执行止损监控
    monitor_stop_loss(context)
    
    # 每周一执行换手控制调仓
    now = context.now
    if now.isoweekday() == 1:
        execute_rotation_with_buffer(context)

def monitor_stop_loss(context):
    positions = get_position()
    for pos in positions:
        symbol = pos['symbol']
        last_bar = history_n(symbol=symbol, frequency='1d', count=1, end_time=context.now, fields='close', df=False)
        if not last_bar: continue
        ret = last_bar[0]['close'] / pos['vwap'] - 1
        if ret <= context.stop_loss:
            order_target_percent(symbol=symbol, percent=0, order_type=OrderType_Market, position_side=PositionSide_Long)
            print(f"{context.now}: 标的 {symbol} 触发硬止损 ({ret:.2%})")

def execute_rotation_with_buffer(context):
    now_str = context.now.strftime('%Y-%m-%d')
    fetch_len = context.training_len + 60
    date_list = get_previous_n_trading_dates(exchange='SHSE', date=now_str, n=fetch_len)
    if not date_list: return
    
    start_date = date_list[0]
    end_date = date_list[-1]
    
    print(f"[*] {context.now}: 启动换手控制回归训练...")
    
    raw_data = history(symbol=context.target_symbols, frequency='1d', start_time=start_date, end_time=end_date, fill_missing='last', df=True)
    raw_data['ret_target'] = raw_data.groupby('symbol')['close'].shift(-context.forecast_len) / raw_data.groupby('symbol')['close'].shift(-1) - 1
    market_median = raw_data.groupby('eob')['ret_target'].transform('median')
    raw_data['alpha_label'] = raw_data['ret_target'] - market_median
    
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
            
    # 风险过滤
    if np.mean(market_vols) * np.sqrt(252) > context.vol_threshold:
        print("[!] 市场风险极高，空仓待机")
        order_close_all()
        return

    # 训练模型
    if len(all_samples) < 5000: return
    X = np.array([s[0] for s in all_samples])
    y = np.array([s[1] for s in all_samples])
    train_data = lgb.Dataset(X, label=y)
    params = {'objective': 'regression', 'metric': 'rmse', 'verbosity': -1, 'learning_rate': 0.05, 'num_leaves': 31, 'seed': 42}
    gbm = lgb.train(params, train_data, num_boost_round=100)
    
    # 预测并排序
    scores = []
    for symbol, x in current_features_map.items():
        pred = gbm.predict(np.array(x).reshape(1, -1))[0]
        scores.append({'symbol': symbol, 'score': pred})
    
    sorted_scores = sorted(scores, key=lambda x: x['score'], reverse=True)
    top_candidates = [s['symbol'] for s in sorted_scores[:context.top_n]]
    tier1_candidates = [s['symbol'] for s in sorted_scores[:context.buffer_n]]
    
    # --- 换手控制逻辑 ---
    current_positions = [pos['symbol'] for pos in get_position()]
    new_picks = []
    
    # 1. 优先保留仍在 Top 5 中的老股票
    for symbol in current_positions:
        if symbol in top_candidates:
            new_picks.append(symbol)
            
    # 2. 如果仓位没满，且有进入 Tier 1 (Top 3) 的新股票，则加入
    for symbol in tier1_candidates:
        if len(new_picks) >= context.top_n: break
        if symbol not in new_picks:
            new_picks.append(symbol)
            
    # 3. 如果还没满，才按顺序补齐
    for symbol in top_candidates:
        if len(new_picks) >= context.top_n: break
        if symbol not in new_picks:
            new_picks.append(symbol)
            
    print(f"[*] 最终调仓决策 (换手控制): {new_picks}")
    
    # 执行
    for symbol in current_positions:
        if symbol not in new_picks:
            order_target_percent(symbol=symbol, percent=0, order_type=OrderType_Market, position_side=PositionSide_Long)
            
    target_percent = 0.95 / len(new_picks) if new_picks else 0
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

def on_backtest_finished(context, indicator):
    print('*'*50)
    result = {"pnl_ratio": indicator.pnl_ratio * 100, "sharpe_ratio": indicator.sharp_ratio, "max_drawdown": indicator.max_drawdown * 100, "win_rate": indicator.win_ratio * 100}
    print('BACKTEST_RESULT_JSON: {}'.format(json.dumps(result)))

if __name__ == '__main__':
    run(strategy_id='79aca4cd-4934-11f1-a57e-da8083a72cab', filename='base_strategy.py', mode=MODE_BACKTEST, token='dc6abd591b356d0f77cc8f224b350312f70050f5', backtest_start_time='2025-11-10 09:00:00', backtest_end_time='2026-05-06 16:00:00', backtest_adjust=ADJUST_PREV, backtest_initial_cash=50000, backtest_commission_ratio=0.0003, backtest_slippage_ratio=0.0001, backtest_match_mode=1)
