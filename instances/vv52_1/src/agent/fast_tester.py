# coding=utf-8
from gm.api import *
import pandas as pd
import json
import os

# Fast Tester Agent: 毫秒级策略仿真器
# 职责：在本地内存中模拟“打板接力”逻辑，用于寻找年化 100% 的最优参数

def run_fast_simulation():
    set_token('dc6abd591b356d0f77cc8f224b350312f70050f5')
    
    # 1. 加载候选基因库
    with open('data/candidates.json', 'r') as f:
        all_candidates = json.load(f)
    
    # 2. 提取所有涉及的标的，一次性获取所有日线行情 (提效关键)
    all_symbols = set()
    for cands in all_candidates.values():
        all_symbols.update(cands)
    all_symbols = list(all_symbols)
    
    print(f"[*] 正在拉取 {len(all_symbols)} 只股票的日线基因...")
    # 获取 2025-11-01 到 2026-05-01 的日线
    history_data = history(symbol=all_symbols, frequency='1d', start_time='2025-11-01', end_time='2026-05-01', fields='symbol,bob,open,close,high,low,pre_close', df=True)
    history_data['bob'] = history_data['bob'].dt.strftime('%Y-%m-%d')
    
    # 建立索引方便查询
    data_map = history_data.set_index(['bob', 'symbol'])
    
    # 3. 模拟逻辑
    cash = 50000
    initial_cash = 50000
    positions = [] # 存储当前持仓 {'symbol', 'buy_price'}
    equity_curve = []
    
    trading_days = sorted(all_candidates.keys())
    
    print("[*] 开始全仓冲刺仿真...")
    
    for i in range(len(trading_days)):
        today = trading_days[i]
        # 仅取每日最强的前 5 名
        today_cands = all_candidates.get(today, [])[:5]
        
        # --- A. 卖出逻辑 ---
        new_positions = []
        for pos in positions:
            symbol = pos['symbol']
            try:
                today_bar = data_map.loc[(today, symbol)]
                limit_price = round(today_bar['pre_close'] * 1.10, 2)
                if today_bar['close'] < limit_price:
                    sell_price = today_bar['close']
                    pnl = (sell_price - pos['buy_price']) / pos['buy_price']
                    cash += pos['value'] * (1 + pnl) * 0.9996
                else:
                    new_positions.append(pos)
            except:
                new_positions.append(pos)
        positions = new_positions

        # --- B. 买入逻辑 (全仓模式) ---
        if len(positions) < 1: # 只拿 1 只最强的
            for symbol in today_cands:
                try:
                    today_bar = data_map.loc[(today, symbol)]
                    limit_price = round(today_bar['pre_close'] * 1.10, 2)
                    if today_bar['high'] >= limit_price:
                        # 全仓投入
                        buy_value = cash
                        cash = 0
                        positions.append({'symbol': symbol, 'buy_price': limit_price, 'value': buy_value})
                        break # 买到 1 只就收工
                except:
                    continue
        
        # 计算今日总资产
        current_equity = cash
        for pos in positions:
            try:
                curr_price = data_map.loc[(today, pos['symbol'])]['close']
                current_equity += pos['value'] * (curr_price / pos['buy_price'])
            except:
                current_equity += pos['value']
        
        equity_curve.append(current_equity)
    
    final_return = (equity_curve[-1] - initial_cash) / initial_cash * 100
    print(f"\n[+] 仿真结束！")
    print(f"最终资产: {equity_curve[-1]:.2f}")
    print(f"累计收益率: {final_return:.2f}%")

if __name__ == '__main__':
    run_fast_simulation()
