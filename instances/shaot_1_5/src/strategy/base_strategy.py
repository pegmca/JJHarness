# coding=utf-8
from __future__ import print_function, absolute_import
from gm.api import *
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

"""
策略逻辑 (v28): 龙头集结-最终版 (Iteration 11)
1. 股票池：中证 1000 (SHSE.000852) 每日成交额前 80 名。
2. 核心排名：选取 [14:50 涨幅 * 0.7 + 量比 * 0.3] 最优的 3 只。
3. 进场信号 (14:50):
   - 涨幅处于 +4.5% 到 +9.8% (10%票) 或 +10% 到 +19.5% (20%票)。
   - 今日成交量 > 1.6 * VMA5。
4. 出场逻辑 (09:35):
   - 封板持有：当前价 >= 涨停价，不卖。
   - 快速止损：亏损 > 4% 立即卖出。
   - 严重低开：低开 > 2% 立即卖出。
   - 获利持盈：盈利 > 10% 后开启 8% 宽幅移动止盈 (拿住大波段)。
   - 动态换仓：3天内涨幅 < 2% 则出场，腾出仓位给新龙头。
5. 仓位：3 只，每只 33% (适度集中)。
"""

def init(context):
    context.max_positions = 3
    context.trailing_pct = 0.08
    context.stop_loss = -0.05
    
    context.target_symbols = []
    context.highest_prices = {}
    context.entry_info = {}
    context.index_constituents = []
    
    schedule(schedule_func=update_pool, date_rule='1d', time_rule='09:31:00')
    schedule(schedule_func=sell_logic, date_rule='1d', time_rule='09:35:00')
    schedule(schedule_func=buy_logic, date_rule='1d', time_rule='14:50:00')
    
    update_pool(context)

def update_pool(context):
    try:
        if not context.index_constituents or context.now.day == 1:
            constituents = stk_get_index_constituents('SHSE.000852')
            context.index_constituents = constituents['symbol'].tolist()
            
        all_symbols = context.index_constituents
        today_str = context.now.strftime('%Y-%m-%d')
        
        data = history(symbol=all_symbols, frequency='1d', start_time=today_str, end_time=today_str, fields='symbol,amount', df=True)
        if data.empty:
            last_day = (context.now - timedelta(days=1)).strftime('%Y-%m-%d')
            data = history(symbol=all_symbols, frequency='1d', start_time=last_day, end_time=last_day, fields='symbol,amount', df=True)
        
        if data.empty: return
        context.target_symbols = data.sort_values(by='amount', ascending=False).head(80)['symbol'].tolist()
    except Exception as e:
        print(f"Error in update_pool: {e}")

def sell_logic(context):
    positions = context.account().positions()
    if not positions: return
        
    symbols = [p['symbol'] for p in positions]
    data = history(symbol=symbols, frequency='1d', start_time=context.now.strftime('%Y-%m-%d'), end_time=context.now.strftime('%Y-%m-%d'), fields='symbol,open,close,pre_close', df=True)
    if data.empty: return
    
    for pos in positions:
        symbol = pos['symbol']
        vwap = pos['vwap']
        if vwap == 0: continue
        
        row = data[data['symbol'] == symbol]
        if row.empty: continue
        row = row.iloc[-1]
        
        price = row['close']
        open_p = row['open']
        pre_close = row['pre_close']
        
        multiplier = 1.2 if symbol.startswith('SZSE.3') or symbol.startswith('SHSE.68') else 1.1
        upper_limit = round(pre_close * multiplier, 2)
        if price >= upper_limit: continue
            
        context.highest_prices[symbol] = max(context.highest_prices.get(symbol, price), price)
        peak = context.highest_prices[symbol]
        pnl = (price - vwap) / vwap
        drawdown = (price - peak) / peak
        
        should_exit = False
        reason = ""
        
        if pre_close > 0 and open_p < pre_close * 0.98:
            should_exit = True
            reason = "低开止损"
        elif pnl <= context.stop_loss:
            should_exit = True
            reason = "硬止损"
        elif pnl > 0.10 and drawdown <= -context.trailing_pct:
            should_exit = True
            reason = "移动止盈"
        elif symbol in context.entry_info:
            hold_days = (context.now.date() - context.entry_info[symbol]['entry_date'].date()).days
            if hold_days >= 3 and pnl < 0.05:
                should_exit = True
                reason = "动态换仓"
            elif hold_days >= 10:
                should_exit = True
                reason = "持有期满"
                
        if should_exit:
            order_target_percent(symbol=symbol, percent=0, order_type=OrderType_Market, position_side=PositionSide_Long)
            print(f"[{context.now}] 出场 {symbol}, 原因: {reason}, PnL: {pnl:.2%}")
            if symbol in context.highest_prices: del context.highest_prices[symbol]
            if symbol in context.entry_info: del context.entry_info[symbol]

def buy_logic(context):
    positions = context.account().positions()
    if len(positions) >= context.max_positions: return
    
    data_hist = history(symbol=context.target_symbols, frequency='1d', start_time=(context.now - timedelta(days=15)).strftime('%Y-%m-%d'), end_time=context.now.strftime('%Y-%m-%d'), fields='symbol,close,volume,pre_close', df=True)
    if data_hist.empty: return
    
    current_pos_symbols = [p['symbol'] for p in positions]
    candidates = []
    
    for symbol, group in data_hist.groupby('symbol'):
        if symbol in current_pos_symbols: continue
        if len(group) < 6: continue
        
        today = group.iloc[-1]
        change = (today['close'] - today['pre_close']) / today['pre_close']
        
        is_20pct = symbol.startswith('SZSE.3') or symbol.startswith('SHSE.68')
        if is_20pct:
            if not (0.10 <= change <= 0.195): continue
        else:
            if not (0.045 <= change <= 0.098): continue
            
        vma5 = group.iloc[:-1]['volume'].tail(5).mean()
        if vma5 == 0: continue
        vr = today['volume'] / vma5
        if vr < 1.6: continue
        
        score = change * 100 + vr * 2
        candidates.append({'symbol': symbol, 'score': score})
        
    if not candidates: return
    candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)
    target_count = context.max_positions - len(positions)
    
    for cand in candidates[:target_count]:
        order_target_percent(symbol=cand['symbol'], percent=1.0/context.max_positions, order_type=OrderType_Market, position_side=PositionSide_Long)
        context.entry_info[cand['symbol']] = {'entry_date': context.now}
        context.highest_prices[cand['symbol']] = today['close']
        print(f"[{context.now}] 入场龙头 {cand['symbol']}, 评分: {cand['score']:.1f}")

def on_backtest_finished(context, indicator):
    import json
    summary = {
        "pnl_ratio": indicator.get('pnl_ratio', 0) * 100,
        "sharpe_ratio": indicator.get('sharpe_ratio', 0),
        "max_drawdown": indicator.get('max_drawdown', 0) * 100,
        "win_rate": indicator.get('win_rate', 0) * 100
    }
    print(f"\nBACKTEST_RESULT_JSON: {json.dumps(summary)}")

if __name__ == '__main__':
    run(strategy_id='ad8f82ec-4591-11f1-b96b-d88083a72cdb', filename='base_strategy.py', mode=MODE_BACKTEST, token='dc6abd591b356d0f77cc8f224b350312f70050f5', backtest_start_time='2025-11-01 09:00:00', backtest_end_time='2026-04-30 16:00:00', backtest_adjust=ADJUST_PREV, backtest_initial_cash=50000, backtest_commission_ratio=0.0003, backtest_slippage_ratio=0.0001)
