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
1. 盘前海选: 利用 history 接口获取 500 只股票昨日数据，完成模型重训和预测（history 不占订阅额度）。
2. 精准订阅: 预测出 Top Picks 和当前持仓后，动态调用 subscribe 只订阅这几十只股票。
3. 动态止盈: 只对已订阅的持仓股进行实时监控。
'''

def init(context):
    # --- 1. 配置海选池 (500只) ---
    df_constituents = stk_get_index_constituents('SHSE.000852')
    context.candidate_pool = df_constituents['symbol'].head(500).tolist()
    
    # 策略核心参数
    context.forecast_len = 2
    context.training_len = 120
    context.top_n = 5
    context.buffer_n = 3
    context.earn_rate = 0.25
    context.stop_loss = -0.08
    context.vol_threshold = 0.45
    
    # --- 2. 初始订阅管理 ---
    # 初始状态只订阅当前持仓 (如果有的话)
    current_symbols = [pos['symbol'] for pos in get_position()]
    if current_symbols:
        subscribe(symbols=current_symbols, frequency='1d')
    
    # --- 3. 定时任务 ---
    # 09:15 盘前海选与重训 (此时全市场历史数据已更新)
    schedule(schedule_func=prepare_and_subscribe, date_rule='1w', time_rule='09:15:00')
    # 09:31 执行调仓
    schedule(schedule_func=execute_rotation_with_buffer, date_rule='1w', time_rule='09:31:00')
    # 每日止损
    schedule(schedule_func=monitor_stop_loss, date_rule='1d', time_rule='09:35:00')
    
    print(f"[{context.now}] 实盘权限适配版初始化完成。")

def prepare_and_subscribe(context):
    """
    盘前海选逻辑：预测全场 500 只，但只订阅 Top Picks
    """
    now_str = context.now.strftime('%Y-%m-%d')
    fetch_len = context.training_len + 60
    date_list = get_previous_n_trading_dates(exchange='SHSE', date=now_str, n=fetch_len)
    if not date_list: return
    
    start_date = date_list[0]
    end_date = date_list[-1]
    
    print(f"[*] {context.now}: [盘前海选] 正在从 500 只标的中筛选 Alpha...")
    
    # 获取海选池历史数据 (注意：history 即使 500 只也不占实时行情名额)
    raw_data = history(symbol=context.candidate_pool, frequency='1d', start_time=start_date, end_time=end_date, fill_missing='last', df=True)
    
    # 数据重训与预测逻辑 (同 V1/V2，但在这里生成 Top Picks)
    # ... (省略中间冗长的特征计算代码，逻辑同前) ...
    # 假设我们通过 LightGBM 得到了 top_candidates
    
    # [关键步骤] 动态订阅
    # 先取消所有旧订阅
    unsubscribe(symbols='*', frequency='1d')
    # 只订阅：Top 10 候选股 + 当前所有持仓股 (总数远小于 50)
    current_positions = [pos['symbol'] for pos in get_position()]
    to_subscribe = list(set(top_candidates + current_positions))
    
    print(f"[*] {context.now}: 动态订阅精选标的 {len(to_subscribe)} 只 (权限合规)")
    subscribe(symbols=to_subscribe, frequency='1d')
    context.active_picks = top_candidates # 存入 context 供 09:31 调仓使用

def execute_rotation_with_buffer(context):
    # 直接使用 09:15 预测好的结果执行调仓
    # ... (原有调仓逻辑) ...
    pass

# ... (后续逻辑保持不变) ...

if __name__ == '__main__':
    run(strategy_id='80aca4cd-4934-11f1-a57e-da8083a72cbd',
        filename='base_strategy.py',
        mode=MODE_LIVE,
        token='dc6abd591b356d0f77cc8f224b350312f70050f5')
