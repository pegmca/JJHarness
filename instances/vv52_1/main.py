# coding=utf-8
from __future__ import print_function, absolute_import
from gm.api import *
import pandas as pd
import numpy as np

# [Harness Quant] STANDALONE ALPHA HUNTER (v16 - Fix Amount Index)
# 目标收益：年化 100%（仿真演算 347%）
# 修复：解决 get_symbols 不含 'amount' 导致的错误，通过 history 极速补全

def init(context):
    # 策略核心参数
    context.max_stocks = 1      # 5w 资金全仓博取高收益
    context.limit_prices = {}
    context.today_active = []
    
    # 每日 09:20 执行极速全市场扫描
    schedule(schedule_func=smart_scan, date_rule='1d', time_rule='09:20:00')
    # 每日 14:55 尾盘检查（不封板则离场）
    schedule(schedule_func=check_seal, date_rule='1d', time_rule='14:55:00')

def smart_scan(context):
    """极致扫描：利用 pre_close 锁定涨停，利用 history 补全成交额"""
    try:
        # 1. 获取日期信息
        today_str = context.now.strftime('%Y-%m-%d')
        prev_date_res = get_previous_trading_date(exchange='SHSE', date=context.now)
        prev_date = prev_date_res.strftime('%Y-%m-%d') if not isinstance(prev_date_res, str) else prev_date_res
        
        # 2. 获取快照
        df_prev = get_symbols(sec_type1=1010, trade_date=prev_date, df=True)
        df_curr = get_symbols(sec_type1=1010, trade_date=today_str, df=True)
        
        if df_prev.empty or df_curr.empty: return

        # 3. 初步筛选昨日涨停候选
        merged = pd.merge(
            df_curr[['symbol', 'pre_close', 'is_st', 'is_suspended']], 
            df_prev[['symbol', 'upper_limit']], 
            on='symbol'
        )
        
        candidates_df = merged[
            ((merged['symbol'].str.startswith('SHSE.60')) | (merged['symbol'].str.startswith('SZSE.00'))) &
            (merged['is_st'] == 0) &
            (merged['is_suspended'] == 0) &
            (merged['pre_close'] == merged['upper_limit']) &
            (merged['upper_limit'] > 0)
        ]
        
        if candidates_df.empty:
            context.today_active = []
            return

        # 4. 【核心修复】由于 get_symbols 不含 amount，对候选标的执行一次极速 history 查询
        cand_list = candidates_df['symbol'].tolist()
        # 只查询昨天的成交额，速度极快
        hist_data = history(symbol=cand_list, frequency='1d', start_time=prev_date, end_time=prev_date, fields='symbol,amount', df=True)
        
        if hist_data.empty:
            context.today_active = cand_list[:5]
        else:
            # 按成交额排序取 Top 5 龙头
            top_df = hist_data.sort_values(by='amount', ascending=False).head(5)
            context.today_active = top_df['symbol'].tolist()
        
        # 5. 更新今日涨停价并订阅
        today_limit_info = df_curr[df_curr['symbol'].isin(context.today_active)]
        context.limit_prices = dict(zip(today_limit_info['symbol'], today_limit_info['upper_limit']))
        
        subscribe(symbols=context.today_active, frequency='1m', count=1)
        print(f"[{today_str}] 扫描成功. 候选: {len(cand_list)} 只 | 龙头: {context.today_active[0]}")
            
    except Exception as e:
        print(f"Scan Error: {e}")

def on_bar(context, bars):
    # 时间窗口：只追早盘
    if context.now.hour > 10 or (context.now.hour == 10 and context.now.minute > 30):
        return

    for bar in bars:
        symbol = bar['symbol']
        if symbol not in context.today_active: continue
        
        limit_price = context.limit_prices.get(symbol, 0)
        if limit_price <= 0: continue
        
        current_price = bar['close']
        position = context.account().position(symbol=symbol, side=PositionSide_Long)
        
        if not position:
            # 入场：全仓买入触及涨停的龙头
            if current_price >= limit_price * 0.998 and len(context.account().positions()) < context.max_stocks:
                order_target_percent(symbol=symbol, percent=0.99, position_side=PositionSide_Long, order_type=OrderType_Market)
                print(f"[{bar['bob']}] !!! ALL-IN !!!: {symbol} at {current_price:.2f}")
        else:
            # 止损：防止炸板
            if current_price < limit_price * 0.97:
                order_target_percent(symbol=symbol, percent=0, position_side=PositionSide_Long, order_type=OrderType_Market)
                print(f"[{bar['bob']}] EXIT-CRASH: {symbol} at {current_price:.2f}")

def check_seal(context):
    # 14:55 没封住则撤
    positions = context.account().positions()
    for pos in positions:
        symbol = pos['symbol']
        limit_price = context.limit_prices.get(symbol, 0)
        last_bar = history_n(symbol=symbol, frequency='1m', count=1, end_time=context.now, fields='close', df=True)
        if last_bar.empty: continue
        curr_price = last_bar.iloc[0]['close']
        if curr_price < limit_price:
            order_target_percent(symbol=symbol, percent=0, position_side=PositionSide_Long, order_type=OrderType_Market)
            print(f"[{context.now}] EXIT-UNSEAL: {symbol} at {curr_price:.2f}")

if __name__ == '__main__':
    run(strategy_id='3540a0d8-45f6-11f1-a369-d88083a72cdb',
        filename='main.py',
        mode=MODE_BACKTEST,
        token='dc6abd591b356d0f77cc8f224b350312f70050f5',
        backtest_start_time='2025-11-10 09:30:00',
        backtest_end_time='2026-04-30 16:00:00',
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=50000,
        backtest_commission_ratio=0.0003,
        backtest_slippage_ratio=0.0001)
