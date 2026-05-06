# coding=utf-8
import subprocess
import os
import re
import json

import sys

# Backtest Runner (Task 1.3)
# 职责：运行策略脚本，捕获输出，提取绩效指标。

def run_backtest(strategy_file):
    print(f"[*] 正在启动回测: {strategy_file}")
    
    python_exe = sys.executable
    log_path = os.path.join('data', 'logs', 'latest_backtest.log')
    
    metrics = {
        "pnl_ratio": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "status": "success"
    }
    
    full_output = []
    try:
        # 使用 Popen 来实时流式输出
        process = subprocess.Popen(
            [python_exe, strategy_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='gbk',
            errors='replace',
            bufsize=1
        )
        
        with open(log_path, 'w', encoding='utf-8') as f:
            for line in process.stdout:
                print(line, end='') # 打印到终端
                f.write(line)
                full_output.append(line)
        
        process.wait()
    except Exception as e:
        print(f"[!] 运行过程发生异常: {e}")
        return {"status": "error", "error": str(e)}
    
    stdout = "".join(full_output)
    
    if process.returncode != 0:
        print(f"[!] 回测运行失败！")
        return {"status": "error", "error": "Return code non-zero"}

    # 解析 JSON 指标
    json_match = re.search(r"BACKTEST_RESULT_JSON:\s*(\{.*\})", stdout)
    if json_match:
        try:
            metrics.update(json.loads(json_match.group(1)))
        except Exception as e:
            print(f"[!] 解析 JSON 指标失败: {e}")
    else:
        # 备用方案：正则匹配
        pnl_match = re.search(r"累计收益率:\s*([\-\d\.]+)%", stdout)
        sharpe_match = re.search(r"夏普比率:\s*([\-\d\.]+)", stdout)
        drawdown_match = re.search(r"最大回撤:\s*([\-\d\.]+)%", stdout)
        
        if pnl_match: metrics["pnl_ratio"] = float(pnl_match.group(1))
        if sharpe_match: metrics["sharpe_ratio"] = float(sharpe_match.group(1))
        if drawdown_match: metrics["max_drawdown"] = float(drawdown_match.group(1))
    
    # 保存指标为 JSON 供 Analyst 读取
    metrics_path = os.path.join('data', 'logs', 'metrics.json')
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=4)
        
    print(f"[+] 回测完成。收益率: {metrics['pnl_ratio']:.2f}%, 夏普: {metrics['sharpe_ratio']:.2f}")
    return metrics

if __name__ == '__main__':
    run_backtest('src/strategy/base_strategy.py')
