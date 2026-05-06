# coding=utf-8
import json
import os

# AI Analyst Agent (Task 2.2)
# 职责：读取回测结果和日志，分析优劣，提出优化建议。

def analyze_performance():
    metrics_path = os.path.join('data', 'logs', 'metrics.json')
    log_path = os.path.join('data', 'logs', 'latest_backtest.log')
    
    if not os.path.exists(metrics_path):
        return "Error: No metrics found."
        
    with open(metrics_path, 'r', encoding='utf-8') as f:
        metrics = json.load(f)
        
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        logs = f.read()

    # 这里本应调用 LLM。在没有 API Key 的自动化脚本中，
    # 我们生成一个专供 Gemini CLI (用户当前的 AI) 阅读的 Prompt。
    
    analysis_prompt = f"""
### 策略回测分析报告
当前收益率: {metrics['pnl_ratio']}%
夏普比率: {metrics['sharpe_ratio']}
最大回撤: {metrics['max_drawdown']}%

#### 交易日志片段:
{logs[-1000:]} 

#### 分析任务:
1. 观察金叉/死叉在 002340 上的表现。
2. 检查是否有频繁交易（交易磨损）。
3. 提出 2-3 点具体的改进建议（例如：引入成交量过滤、改变均线周期、加入止损逻辑）。
"""
    
    analysis_report_path = os.path.join('data', 'logs', 'analysis_report.md')
    with open(analysis_report_path, 'w', encoding='utf-8') as f:
        f.write(analysis_prompt)
        
    print(f"[+] 分析报告已生成: {analysis_report_path}")
    return analysis_prompt

if __name__ == '__main__':
    analyze_performance()
