# coding=utf-8
from gm.api import *
import pandas as pd
import json
import os

# Explorer Agent v2: 深度挖掘 + 排序
# 职责：识别涨停的同时，按成交额(amount)排序，只取每日最强的 Top 10

def precompute_refined_candidates(start_date, end_date):
    set_token('dc6abd591b356d0f77cc8f224b350312f70050f5')
    print(f"[*] 开始提效扫描: {start_date} -> {end_date}")
    
    trading_days = get_trading_dates(exchange='SHSE', start_date=start_date, end_date=end_date)
    results = {}
    
    symbols_info = get_symbols(sec_type1=1010, df=True)
    main_board_pool = symbols_info[
        (symbols_info['symbol'].str.startswith('SHSE.60')) | 
        (symbols_info['symbol'].str.startswith('SZSE.00'))
    ]['symbol'].tolist()
    
    for i in range(1, len(trading_days)):
        prev_day = trading_days[i-1]
        curr_day = trading_days[i]
        
        print(f"扫描中: {prev_day}...", end='\r')
        
        try:
            # 获取昨日行情，包含成交额 amount
            market_data = history(symbol=main_board_pool, frequency='1d', start_time=prev_day, end_time=prev_day, fields='symbol,close,pre_close,high,low,amount', df=True)
            if market_data.empty: continue
            
            market_data['limit_price'] = (market_data['pre_close'] * 1.10).round(2)
            
            # 筛选昨日封板且非一字
            cand_df = market_data[
                (abs(market_data['close'] - market_data['limit_price']) < 0.01) & 
                (market_data['high'] > market_data['low'])
            ]
            
            # 【核心优化】按成交额从高到低排序，只取前 10 名（人气龙头）
            top_cands = cand_df.sort_values(by='amount', ascending=False).head(10)['symbol'].tolist()
            
            results[curr_day] = top_cands
        except Exception as e:
            print(f"\n[!] {prev_day} 报错: {e}")

    save_path = os.path.join('data', 'candidates.json')
    with open(save_path, 'w') as f:
        json.dump(results, f)
        
    print(f"\n[+] 提效基因库生成！每日仅监控 Top 10 人气股。保存至: {save_path}")

if __name__ == '__main__':
    precompute_refined_candidates('2025-11-01', '2026-05-01')
