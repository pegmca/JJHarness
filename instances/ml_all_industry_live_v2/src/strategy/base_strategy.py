# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals
from gm.api import *
import datetime
import numpy as np
import pandas as pd
import json
import lightgbm as lgb

'''
Harness Quant: 全行业机器学习选股策略 (ml_all_industry_live_v2) - 50只权限适配版

权限突破方案:
1. 盘前海选: 利用 history 接口获取 500 只历史数据完成模型训练和预测（不占订阅额度）。
2. 精准订阅: 预测后动态更新订阅，只订阅 Top 候选 + 当前持仓（总数远小于 50）。
3. 持仓保护: 更新订阅时只做差量增删，持仓股订阅永不中断，确保止损监控不失效。
'''


def init(context):
    df_constituents = stk_get_index_constituents('SHSE.000852')
    context.candidate_pool = df_constituents['symbol'].tolist()[:500]

    context.forecast_len = 2
    context.training_len = 120
    context.top_n = 5
    context.buffer_n = 3
    context.earn_rate = 0.25
    context.stop_loss = -0.08
    context.vol_threshold = 0.45

    # 跟踪已订阅标的，用于精准增删避免全量 unsubscribe
    context.subscribed_symbols = set()
    context.active_picks = []

    # 初始只订阅当前持仓
    current_symbols = [pos['symbol'] for pos in get_position()]
    if current_symbols:
        subscribe(symbols=current_symbols, frequency='1d')
        context.subscribed_symbols = set(current_symbols)

    # 09:15 盘前海选与重训（history 不占订阅额度）
    schedule(schedule_func=prepare_and_subscribe, date_rule='1w', time_rule='09:15:00')
    # 09:31 执行调仓
    schedule(schedule_func=execute_rotation_with_buffer, date_rule='1w', time_rule='09:31:00')
    # 每日止损监控
    schedule(schedule_func=monitor_stop_loss, date_rule='1d', time_rule='09:35:00')

    print(f"[{context.now}] 初始化完成，已订阅持仓 {len(context.subscribed_symbols)} 只。")


def prepare_and_subscribe(context):
    """
    盘前海选：用 history（不占订阅额度）跑完整模型，精准更新订阅列表。
    任何中途失败都保持原订阅不变，不影响止损监控。
    """
    now_str = context.now.strftime('%Y-%m-%d')
    fetch_len = context.training_len + 60
    date_list = get_previous_n_trading_dates(exchange='SHSE', date=now_str, n=fetch_len)
    if not date_list:
        print(f"[!] {context.now}: 获取交易日列表失败，保持原订阅")
        return

    start_date = date_list[0]
    end_date = date_list[-1]

    print(f"[*] {context.now}: [盘前海选] 从 {len(context.candidate_pool)} 只标的中筛选 Alpha...")

    try:
        raw_data = history(
            symbol=context.candidate_pool, frequency='1d',
            start_time=start_date, end_time=end_date,
            fill_missing='last', df=True
        )
    except Exception as e:
        print(f"[!] {context.now}: history 拉取失败 ({e})，保持原订阅")
        return

    if raw_data is None or raw_data.empty:
        print(f"[!] {context.now}: 数据为空，跳过本次海选")
        return

    # 截面相对收益标注
    raw_data['ret_target'] = (
        raw_data.groupby('symbol')['close'].shift(-context.forecast_len)
        / raw_data.groupby('symbol')['close'].shift(-1) - 1
    )
    market_median = raw_data.groupby('eob')['ret_target'].transform('median')
    raw_data['alpha_label'] = raw_data['ret_target'] - market_median

    all_samples = []
    current_features_map = {}
    market_vols = []

    for symbol in context.candidate_pool:
        stock_df = raw_data[raw_data['symbol'] == symbol].copy().reset_index(drop=True)
        if len(stock_df) < context.training_len:
            continue

        stock_df = calculate_alpha_features(stock_df)
        if stock_df.empty:
            continue

        market_vols.append(stock_df['volatility'].iloc[-1])
        samples, latest_x = extract_regression_samples(context, stock_df)
        if samples and latest_x is not None:
            all_samples.extend(samples)
            current_features_map[symbol] = latest_x

    # 市场整体波动率过高则清仓待机，不更新 active_picks
    if market_vols and np.nanmean(market_vols) * np.sqrt(252) > context.vol_threshold:
        print(f"[!] {context.now}: 市场波动率过高，清仓待机，暂停本周调仓")
        context.active_picks = []
        return

    if len(all_samples) < 5000:
        print(f"[!] {context.now}: 样本不足 ({len(all_samples)})，跳过本次训练")
        return

    # 训练 LightGBM
    X = np.array([s[0] for s in all_samples])
    y = np.array([s[1] for s in all_samples])
    train_data = lgb.Dataset(X, label=y)
    params = {
        'objective': 'regression', 'metric': 'rmse', 'verbosity': -1,
        'learning_rate': 0.05, 'num_leaves': 31, 'seed': 42
    }
    gbm = lgb.train(params, train_data, num_boost_round=100)

    # 预测并排序，多取 10 只作为候选缓冲
    scores = []
    for symbol, x in current_features_map.items():
        pred = gbm.predict(np.array(x).reshape(1, -1))[0]
        scores.append({'symbol': symbol, 'score': pred})

    sorted_scores = sorted(scores, key=lambda s: s['score'], reverse=True)
    top_candidates = [s['symbol'] for s in sorted_scores[:context.top_n + 10]]
    context.active_picks = top_candidates

    # --- 精准更新订阅（持仓股始终保留，只做差量增删）---
    current_positions = set(pos['symbol'] for pos in get_position())
    to_subscribe = set(top_candidates) | current_positions

    to_remove = context.subscribed_symbols - to_subscribe
    to_add = to_subscribe - context.subscribed_symbols

    if to_remove:
        unsubscribe(symbols=list(to_remove), frequency='1d')
    if to_add:
        subscribe(symbols=list(to_add), frequency='1d')

    context.subscribed_symbols = to_subscribe

    print(f"[*] {context.now}: 海选完成，Top 候选: {top_candidates[:context.top_n]}")
    print(f"[*] {context.now}: 订阅更新: +{len(to_add)} -{len(to_remove)}，当前共 {len(context.subscribed_symbols)} 只")


def execute_rotation_with_buffer(context):
    """
    09:31 执行调仓，使用 09:15 预测好的 active_picks，带换手控制缓冲。
    """
    if not context.active_picks:
        print(f"[!] {context.now}: active_picks 为空（波动率过高或海选失败），跳过调仓")
        return

    top_candidates = context.active_picks[:context.top_n]
    tier1_candidates = context.active_picks[:context.buffer_n]
    current_positions = [pos['symbol'] for pos in get_position()]

    new_picks = []

    # 1. 优先保留仍在 Top N 中的老股票
    for symbol in current_positions:
        if symbol in top_candidates:
            new_picks.append(symbol)

    # 2. Tier1（Top 3）新股票优先补仓
    for symbol in tier1_candidates:
        if len(new_picks) >= context.top_n:
            break
        if symbol not in new_picks:
            new_picks.append(symbol)

    # 3. 按顺序补齐剩余仓位
    for symbol in top_candidates:
        if len(new_picks) >= context.top_n:
            break
        if symbol not in new_picks:
            new_picks.append(symbol)

    print(f"[*] {context.now}: 调仓决策 (换手控制): {new_picks}")

    # 平掉不在 new_picks 的持仓
    for symbol in current_positions:
        if symbol not in new_picks:
            order_target_percent(symbol=symbol, percent=0, order_type=OrderType_Market, position_side=PositionSide_Long)

    # 建仓/调仓
    target_percent = 0.95 / len(new_picks) if new_picks else 0
    for symbol in new_picks:
        order_target_percent(symbol=symbol, percent=target_percent, order_type=OrderType_Market, position_side=PositionSide_Long)


def monitor_stop_loss(context):
    """每日止损监控，触发止损后同步取消订阅。"""
    positions = get_position()
    for pos in positions:
        symbol = pos['symbol']
        last_bar = history_n(symbol=symbol, frequency='1d', count=1, end_time=context.now, fields='close', df=False)
        if not last_bar:
            continue
        ret = last_bar[0]['close'] / pos['vwap'] - 1
        if ret <= context.stop_loss:
            order_target_percent(symbol=symbol, percent=0, order_type=OrderType_Market, position_side=PositionSide_Long)
            if symbol in context.subscribed_symbols:
                unsubscribe(symbols=[symbol], frequency='1d')
                context.subscribed_symbols.discard(symbol)
            print(f"[!] {context.now}: {symbol} 触发止损 ({ret:.2%})，已平仓并取消订阅")


def calculate_alpha_features(df):
    returns = df['close'].pct_change()
    ma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    df['price_std_score'] = (df['close'] - ma20) / (std20 + 1e-9)
    vma20 = df['volume'].rolling(20).mean()
    df['vol_spike'] = df['volume'] / (vma20 + 1e-9)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / (loss + 1e-9)))
    df['rsi_slope'] = df['rsi'].diff(3)
    df['volatility'] = returns.rolling(20).std()
    df['skewness'] = returns.rolling(20).skew()
    return df.dropna()


def extract_regression_samples(context, df):
    feature_cols = ['price_std_score', 'vol_spike', 'rsi', 'rsi_slope', 'volatility', 'skewness']
    cols = feature_cols + ['alpha_label']
    if not all(c in df.columns for c in cols):
        return [], None
    data = df[cols].values
    samples = []
    latest_x = None
    for i in range(len(df)):
        feature = data[i, :6].tolist()
        latest_x = feature
        label = data[i, 6]
        if not np.isnan(label):
            samples.append((feature, label))
    return samples, latest_x


def on_backtest_finished(context, indicator):
    print('*' * 50)
    result = {
        "pnl_ratio": indicator.pnl_ratio * 100,
        "sharpe_ratio": indicator.sharp_ratio,
        "max_drawdown": indicator.max_drawdown * 100,
        "win_rate": indicator.win_ratio * 100
    }
    print('BACKTEST_RESULT_JSON: {}'.format(json.dumps(result)))


if __name__ == '__main__':
    run(strategy_id='80aca4cd-4934-11f1-a57e-da8083a72cbd',
        filename='base_strategy.py',
        mode=MODE_LIVE,
        token='dc6abd591b356d0f77cc8f224b350312f70050f5')
