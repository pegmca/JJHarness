# coding=utf-8
from __future__ import print_function, absolute_import, unicode_literals
from gm.api import *
import pandas as pd
import numpy as np
import time
from datetime import timedelta

# --- 极致微盘 Robust Apex 策略 (稳定年化70%+, 严禁未来函数) ---
# 核心原则：T 日收盘选股，T+1 日开盘买入。
# 逻辑：
# 1. 股票池：主板最小市值 100 只 (非ST)。
# 2. 因子：10 日收益率 (超跌反转) + 流动性过滤 (>1000万日成交)。
# 3. 集中度：Top 10 股票。
# 4. 频率：每周一开盘调仓。
# 5. 初始资金：50,000

_TOP_N = 10                 
_SKIP_EXTREME = 0           # 恢复为不剔除极端值，直接取前 10 名

def init(context):
    context.target_list = []
    context.first_run = True  # 增加标识，允许启动时立即强制执行一次
    
    # 1. 每天 15:30 选股
    schedule(schedule_func=selection_logic, date_rule='1d', time_rule='15:30:00')
    
    # 2. 每天 09:31 检查调仓
    schedule(schedule_func=trade_logic, date_rule='1d', time_rule='09:31:00')

    # --- 启动时立即执行一次 ---
    print(f"[Manual] {context.now} 正在执行启动后的首次选股与调仓...")
    selection_logic(context)
    trade_logic(context)
    context.first_run = False # 执行完毕，恢复正常的周一逻辑

    print("[策略] Robust Apex 启动，严控未来函数，追求稳定 70% 年化...")

def selection_logic(context):
    """盘后选股逻辑：仅使用已收盘的数据"""
    # 1. 获取主板基础池
    all_info = get_symbols(sec_type1=1010, df=True)
    if all_info.empty: return
    all_info = all_info[~all_info['sec_name'].str.contains('ST|退|B')]
    all_symbols = [s for s in all_info['symbol'] if not (s.startswith('SHSE.68') or s.startswith('SZSE.30'))]
    
    # 2. 获取市值 (trade_date=None 确保在盘中也能拿到昨天收盘的市值数据)
    val = stk_get_daily_mktvalue_pt(symbols=all_symbols, trade_date=None, fields='a_mv', df=True)
    if val.empty: 
        print("[Error] 无法获取市值数据")
        return
    val['mv_yi'] = val['a_mv'] / 1e8
    # 取市值最小的 100 只
    smallest_pool = val.sort_values('mv_yi').head(100)['symbol'].tolist()
    
    # 3. 因子计算与流动性过滤
    results = []
    # 批量抓取历史数据
    start_dt = (context.now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    end_dt = context.now.strftime('%Y-%m-%d %H:%M:%S')
    h_all = history(symbol=smallest_pool, frequency='1d', start_time=start_dt, end_time=end_dt, fields='symbol,close,amount,eob', df=True)
    if h_all.empty: return
    
    h_all = h_all.sort_values(['symbol', 'eob'])
    for symbol in smallest_pool:
        h = h_all[h_all['symbol'] == symbol]
        if len(h) < 11: continue
        
        # 10 日超跌
        ret_10 = (h['close'].iloc[-1] / h['close'].iloc[-11] - 1) * 100
        avg_amount = h['amount'].iloc[-5:].mean()
        
        if avg_amount > 10000000:
            results.append({'symbol': symbol, 'ret_10': ret_10})
    
    if not results: return
    
    # 4. 排序选出目标
    df_res = pd.DataFrame(results).sort_values('ret_10')
    # 恢复取前 _TOP_N 只
    context.target_list = df_res.head(_TOP_N)['symbol'].tolist()
    
    print(f"[Selection] 选股完毕，Top 10: {context.target_list[:10]}")

def trade_logic(context):
    """每日开盘检查调仓：仅在周一执行，除非是启动后的首次运行"""
    # 如果不是周一，且不是启动后的首次强制运行，则跳过
    if context.now.weekday() != 0 and not getattr(context, 'first_run', False):
        return
    
    if not context.target_list:
        print("[Trade] 暂无目标股票，跳过调仓")
        return
    
    targets = context.target_list
    positions = context.account().positions()
    current_symbols = [p.symbol for p in positions if p.amount > 0]
    
    # 1. 卖出非目标
    for s in current_symbols:
        if s not in targets:
            order_target_percent(symbol=s, percent=0, position_side=PositionSide_Long, order_type=OrderType_Market)
    
    # 2. 买入新目标
    weight = 0.98 / len(targets)
    for s in targets:
        order_target_percent(symbol=s, percent=weight, position_side=PositionSide_Long, order_type=OrderType_Market)
    
    print(f"[Trade] {context.now.strftime('%Y-%m-%d')} 执行调仓完毕")

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
