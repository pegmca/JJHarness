from gm.api import *
import pandas as pd
from datetime import datetime, timedelta

def init(context):
    symbols = 'SHSE.600000,SZSE.000001'
    # Test history with start_time
    start_time = (context.now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S')
    try:
        data = history(symbol=symbols, frequency='1d', start_time=start_time, end_time=context.now, df=True)
        print("History with start_time success")
        print(data.head())
    except Exception as e:
        print(f"History with start_time failed: {e}")

    # Test history_n with one symbol
    try:
        data = history_n(symbol='SHSE.600000', frequency='1d', count=5, end_time=context.now, df=True)
        print("History_n with one symbol success")
    except Exception as e:
        print(f"History_n with one symbol failed: {e}")

    # Test history_n with multiple symbols
    try:
        data = history_n(symbol=symbols, frequency='1d', count=5, end_time=context.now, df=True)
        print("History_n with multiple symbols success")
    except Exception as e:
        print(f"History_n with multiple symbols failed: {e}")

    context.quit()

if __name__ == '__main__':
    run(strategy_id='test', filename='test_history.py', mode=MODE_BACKTEST, token='dc6abd591b356d0f77cc8f224b350312f70050f5', backtest_start_time='2026-04-01 09:00:00', backtest_end_time='2026-04-01 15:00:00')
