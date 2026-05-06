# coding=utf-8
from __future__ import print_function, absolute_import
from gm.api import *
import pandas as pd
import numpy as np
import json

# 基础策略 (v37 极限复利版 - 无未来函数)
# 核心逻辑：
# 1. 初始资金 50,000，杠杆率 99.5%。
# 2. 零阈值突破：价格突破前高 + 成交量略微放大（>1.05x MA），第一时间进场。
# 3. 稳健追踪：1.8*ATR 追踪止损，给动能留出合理的“呼吸”空间，避免被洗。
# 4. 极致回补：5 个 Bar 内强势重回趋势线则立即买回。
# 5. 目标：5个月累计收益 > 42% (年化 > 100%)。

def init(context):
    context.symbol = 'SZSE.002340'
    subscribe(symbols=context.symbol, frequency='15m', count=100, wait_group=True)
    
    # 策略参数
    context.atr_n = 14
    context.highest_price = 0
    context.last_exit_price = 0
    context.reentry_window = 0

def on_bar(context, bars):
    bar = bars[0]
    symbol = bar['symbol']
    
    data = history_n(symbol=symbol, frequency='15m', count=100, end_time=bar['eob'], fields='close,high,low,volume', df=True)
    if len(data) < 30: return
    
    closes = data['close'].values
    highs = data['high'].values
    volumes = data['volume'].values
    
    # 动能指标
    ema5 = pd.Series(closes).ewm(span=5).mean().values[-1]
    prev_high = highs[-2]
    vol_ma = np.mean(volumes[-11:-1])
    
    # ATR
    tr = np.maximum(data['high'].values[1:] - data['low'].values[1:], 
                   np.maximum(np.abs(data['high'].values[1:] - closes[:-1]), 
                             np.abs(data['low'].values[1:] - closes[:-1])))
    atr = np.mean(tr[-context.atr_n:])
    
    position = context.account().position(symbol=symbol, side=PositionSide_Long)
    has_position = position is not None and position['volume'] > 0
    
    # 交易逻辑
    if not has_position:
        # A: 零阈值突破入场
        enter_signal = bar['close'] > prev_high and bar['volume'] > vol_ma * 1.05
        
        # B: 极速回补
        re_enter_signal = (context.reentry_window > 0 and 
                           bar['close'] > context.last_exit_price * 1.001 and 
                           bar['close'] > ema5)
        
        if enter_signal or re_enter_signal:
            order_target_percent(symbol=symbol, percent=0.995, position_side=PositionSide_Long, order_type=OrderType_Market)
            context.highest_price = bar['close']
            context.reentry_window = 0
            print(f"{bar['eob']} - [V37极限入场] 价格: {bar['close']:.2f}, RE:{re_enter_signal}")
    else:
        context.highest_price = max(context.highest_price, bar['close'])
        
        # 稳健追踪止损：1.8 * ATR
        stop_line = context.highest_price - 1.8 * atr
        
        if bar['close'] < stop_line or bar['close'] < ema5:
            order_target_percent(symbol=symbol, percent=0, position_side=PositionSide_Long, order_type=OrderType_Market)
            context.last_exit_price = bar['close']
            context.reentry_window = 5 # 回补窗口
            print(f"{bar['eob']} - [V37利润锁定] 价格: {bar['close']:.2f}")
            context.highest_price = 0
    
    if context.reentry_window > 0:
        context.reentry_window -= 1

def on_backtest_finished(context, indicator):
    summary = {
        "pnl_ratio": indicator.get('pnl_ratio', 0) * 100,
        "sharpe_ratio": indicator.get('sharpe_ratio', 0),
        "max_drawdown": indicator.get('max_drawdown', 0) * 100
    }
    print(f"\nBACKTEST_RESULT_JSON: {json.dumps(summary)}")

if __name__ == '__main__':
    run(strategy_id='c3d44bc2-458d-11f1-b96b-d88083a72cdb',
        filename='base_strategy.py',
        mode=MODE_BACKTEST,
        token='dc6abd591b356d0f77cc8f224b350312f70050f5',
        backtest_start_time='2025-12-01 08:00:00',
        backtest_end_time='2026-04-30 16:00:00',
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=50000,
        backtest_commission_ratio=0.0003,
        backtest_slippage_ratio=0.0001)
