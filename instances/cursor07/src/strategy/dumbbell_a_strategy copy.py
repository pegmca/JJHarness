# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals
from gm.api import *
import pandas as pd
import numpy as np
import time
from datetime import timedelta

# --- 极致微盘 Compounder Apex 策略 (最高胜率+超高收益版) ---
# 核心逻辑：
# 1. 股票池：主板最小市值 100 只 (避开科创/创业板的高波动，聚焦主板壳价值)。
# 2. 因子：10 日收益率 (Worst 10-day return, 寻找技术性坑位)。
# 3. 集中度：Top 10 股票 (最优分散度，确保稳健复利)。
# 4. 择时：单日极速暴跌 5% 熔断。
# 5. 权重：100% 满仓滚动 (极致利用 5w 初始资金)。
# 6. 频率：每周一 14:45 轮动。

_TOP_N = 10                 

def init(context):
    # 每周一执行选股调仓
    schedule(schedule_func=weekly_operation, date_rule='1w', time_rule='14:45:00')
    # 每天同步检查极端大盘崩溃
    schedule(schedule_func=market_timing, date_rule='1d', time_rule='09:31:00')

    print("[策略] Compounder Apex 启动，开启 5 年复利之旅...")

def weekly_operation(context):
    """每周选股调仓一站式操作"""
    start_time = time.time()
    now_date = context.now.strftime('%Y-%m-%d')
    
    # 1. 获取基础股票池
    all_info = get_symbols(sec_type1=1010, df=True)
    if all_info.empty: return
    all_info = all_info[~all_info['sec_name'].str.contains('ST|退|B')]
    # 聚焦主板 (SHSE.60 / SZSE.00)
    all_symbols = [s for s in all_info['symbol'] if not (s.startswith('SHSE.68') or s.startswith('SZSE.30'))]
    
    # 2. 市值筛选
    val = stk_get_daily_mktvalue_pt(symbols=all_symbols, trade_date=now_date, fields='a_mv', df=True)
    if val.empty: return
    val['mv_yi'] = val['a_mv'] / 1e8
    smallest_pool = val.sort_values('mv_yi').head(100)['symbol'].tolist()
    
    # 3. 10 日超跌因子计算
    results = []
    for symbol in smallest_pool:
        h = history_n(symbol=symbol, frequency='1d', count=11, end_time=context.now, fields='close', df=True)
        if len(h) < 11: continue
        ret_10 = (h['close'].iloc[-1] / h['close'].iloc[0] - 1) * 100
        results.append({'symbol': symbol, 'ret_10': ret_10})
    
    if not results: return
    df_res = pd.DataFrame(results).sort_values('ret_10')
    targets = df_res.head(_TOP_N)['symbol'].tolist()
    
    # 4. 调仓执行
    positions = context.account().positions()
    current_symbols = [p.symbol for p in positions if p.amount > 0]
    
    # 先清理非目标
    for s in current_symbols:
        if s not in targets:
            order_target_percent(symbol=s, percent=0, position_side=PositionSide_Long, order_type=OrderType_Market)
    
    # 均匀分配 100% 仓位
    weight = 1.0 / len(targets)
    for s in targets:
        order_target_percent(symbol=s, percent=weight, position_side=PositionSide_Long, order_type=OrderType_Market)
        
    duration = time.time() - start_time
    print(f"[Weekly Operation] {now_date} 完成，耗时: {duration:.2f}s, 目标数: {len(targets)}")

def market_timing(context):
    """5% 极端暴跌全场熔断"""
    idx_h = history_n(symbol='SHSE.000001', frequency='1d', count=2, end_time=context.now, fields='open,close', df=True)
    if len(idx_h) >= 2:
        prev_o, prev_c = idx_h['open'].iloc[0], idx_h['close'].iloc[0]
        if prev_o > 0 and prev_c / prev_o <= 0.95:
            print("[大盘] 极端风险，强制清仓避险")
            order_close_all()

def order_close_all():
    positions = get_position()
    for p in positions:
        if p.amount > 0:
            order_target_percent(symbol=p.symbol, percent=0, position_side=PositionSide_Long, order_type=OrderType_Market)

def on_backtest_finished(context, indicator):
    import json
    res = {
        "pnl_ratio": getattr(indicator, 'pnl_ratio', 0) * 100,
        "sharp_ratio": getattr(indicator, 'sharp_ratio', 0),
        "max_drawdown": getattr(indicator, 'max_drawdown', 0) * 100,
        "pnl_annual": getattr(indicator, 'pnl_annual', 0) * 100
    }
    print(f"\nBACKTEST_RESULT_JSON: {json.dumps(res)}")

if __name__ == '__main__':
    run(strategy_id='7a0e9266-462c-11f1-a369-d88083a72cdb',
        filename='dumbbell_a_strategy.py',
        mode=MODE_BACKTEST,
        token='dc6abd591b356d0f77cc8f224b350312f70050f5',
        backtest_start_time='2021-01-01 08:00:00',
        backtest_end_time='2026-04-30 16:00:00',
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=50000,
        backtest_commission_ratio=0.0003,
        backtest_slippage_ratio=0.0001)
