# coding=utf-8
from gm.api import *
import pandas as pd

# 数据探索脚本
# 职责：拉取最近 180 天的数据并计算基础指标，诊断为什么策略不成交。

def explore():
    set_token('dc6abd591b356d0f77cc8f224b350312f70050f5')
    symbol = 'SZSE.002340'
    
    # 获取日线数据
    data = history(symbol=symbol, frequency='1d', start_time='2026-01-01', end_time='2026-04-30', df=True)
    if data.empty:
        print("[!] 未获取到数据，请检查权限或日期。")
        return

    # 计算 10/30 均线
    data['ma10'] = data['close'].rolling(10).mean()
    data['ma30'] = data['close'].rolling(30).mean()
    data['uptrend'] = data['ma10'] > data['ma30']
    
    uptrend_days = data['uptrend'].sum()
    print(f"[*] 数据总量: {len(data)} 天")
    print(f"[*] 上涨趋势天数 (MA10 > MA30): {uptrend_days} 天")
    print(f"[*] 最近价格: {data['close'].iloc[-1]}, MA10: {data['ma10'].iloc[-1]:.2f}, MA30: {data['ma30'].iloc[-1]:.2f}")
    
    if uptrend_days == 0:
        print("[!] 诊断结果：日线级别长期处于下跌或横盘，多周期策略（日线金叉）无法入场。")
        print("[建议]：缩短趋势判定周期（如 MA5/MA10）或加入反弹/波段逻辑。")

if __name__ == '__main__':
    explore()
