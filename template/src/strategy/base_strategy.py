# coding=utf-8
from __future__ import print_function, absolute_import
from gm.api import *
import pandas as pd
import numpy as np
from datetime import datetime

# [TEMPLATE] 基础策略模板
# 优化方向：修改指标、逻辑、频率，并配合 Ralph Loop 自动迭代。

def init(context):
    # 请修改为你想要交易的标的
    context.symbol = 'SHSE.600000'
    subscribe(symbols=context.symbol, frequency='15m', count=50, wait_group=True)
    
    # 策略参数
    context.n = 20
    context.k = 2.0
    context.atr_n = 14
    context.highest_price = 0

def on_bar(context, bars):
    bar = bars[0]
    symbol = bar['symbol']
    
    # 获取数据并计算逻辑
    data = history_n(symbol=symbol, frequency='15m', count=context.n + 10, end_time=bar['eob'], fields='close,high,low', df=True)
    if len(data) < context.n + 1: return
    
    # ... 实现你的交易逻辑 ...

def on_backtest_finished(context, indicator):
    import json
    summary = {
        "pnl_ratio": indicator.get('pnl_ratio', 0) * 100,
        "sharpe_ratio": indicator.get('sharpe_ratio', 0),
        "max_drawdown": indicator.get('max_drawdown', 0) * 100
    }
    print(f"\nBACKTEST_RESULT_JSON: {json.dumps(summary)}")

if __name__ == '__main__':
    run(strategy_id='',
        filename='base_strategy.py',
        mode=MODE_BACKTEST,
        token='dc6abd591b356d0f77cc8f224b350312f70050f5',
        backtest_start_time='2025-11-10 08:00:00',
        backtest_end_time='2026-04-30 16:00:00',
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=50000,
        backtest_commission_ratio=0.0003,
        backtest_slippage_ratio=0.0001)
