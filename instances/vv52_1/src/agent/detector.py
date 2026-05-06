# coding=utf-8
import os
import re

# AI Future Function Detector Agent
# 职责：检测代码中是否存在未来函数（Look-ahead Bias），确保回测的真实性。

def detect_future_functions():
    strategy_path = os.path.join('src', 'strategy', 'base_strategy.py')
    
    if not os.path.exists(strategy_path):
        return "Error: Strategy file not found."
        
    with open(strategy_path, 'r', encoding='utf-8') as f:
        code = f.read()

    # 未来函数检测规则（示例）
    rules = [
        {
            "name": "History Look-ahead",
            "pattern": r"history_n\(.*end_time\s*=\s*[^,]*\)",
            "description": "调用 history_n 时必须确保 end_time 不超过当前 bar 的 eob 或当前时间。"
        },
        {
            "name": "Future Fundamental Data",
            "pattern": r"get_fundamentals\(.*date\s*=\s*[^,]*\)",
            "description": "查询财务数据时使用的 date 必须在当前回测时间之前。"
        },
        {
            "name": "Invalid Slice/Index",
            "pattern": r"data\[.*:.*\]",
            "description": "对行情切片时，严禁使用超出当前索引的切片（如 data[i+1]）。"
        }
    ]

    findings = []
    for rule in rules:
        if re.search(rule['pattern'], code):
            findings.append(f"- **{rule['name']}**: {rule['description']}")

    # 硬性约束检查
    if not re.search(r"backtest_initial_cash\s*=\s*50000", code):
        findings.append("- **Initial Cash Error**: [硬约束] backtest_initial_cash 必须严格设置为 50000（5w）。")
    if not re.search(r"backtest_commission_ratio\s*=\s*0.0003", code):
        findings.append("- **Commission Error**: [硬约束] backtest_commission_ratio 必须设置为 0.0003（万三手续费）。")
    if not re.search(r"backtest_slippage_ratio\s*=\s*0.0001", code):
        findings.append("- **Slippage Error**: [硬约束] backtest_slippage_ratio 必须设置为 0.0001（万一滑点）。")

    # 生成检测报告
    detection_prompt = f"""
### 未来函数检测报告
检测目标：`src/strategy/base_strategy.py`

#### 自动规则匹配结果：
{chr(10).join(findings) if findings else "未发现明显的硬编码未来函数模式。"}

#### 审计任务：
请人工或利用 LLM 深度审查代码中的逻辑，重点检查：
1. `on_bar` 或 `on_tick` 中是否引用了回测时刻之后的行情数据。
2. 均线或技术指标计算是否包含了“未来”的 K 线。
3. 调仓逻辑是否在已知结果后才触发。

**如果发现未来函数，必须立即修正，严禁输出带有未来函数的代码进行回测！**
"""
    
    report_path = os.path.join('data', 'logs', 'detector_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(detection_prompt)
        
    print(f"[+] 未来函数检测报告已生成: {report_path}")
    return detection_prompt

if __name__ == '__main__':
    detect_future_functions()
