# coding=utf-8
import os

# AI Coder Agent (Task 2.1)
# 职责：根据分析建议修改代码。

def apply_improvements(improvement_suggestions):
    strategy_path = os.path.join('src', 'strategy', 'base_strategy.py')
    
    if not os.path.exists(strategy_path):
        return "Error: Strategy file not found."
        
    with open(strategy_path, 'r', encoding='utf-8') as f:
        code = f.read()

    # 在全自动模式下，这个脚本会向 LLM 发送 code + suggestions
    # 并将返回的新代码写入文件。
    # 这里我们生成一个指令文件供外部调度器（Gemini CLI）执行。
    
    coder_instruction = f"""
### 程序员任务
参考以下优化建议，修改 `src/strategy/base_strategy.py`：
{improvement_suggestions}

**【硬性要求】回测参数必须保持一致，不得修改：**
1. 初始资金(backtest_initial_cash): 50000 (5w)
2. 手续费(backtest_commission_ratio): 0.0003 (万三)
3. 滑点(backtest_slippage_ratio): 0.0001 (万一)

请直接输出修改后的完整 Python 代码。
"""
    
    instruction_path = os.path.join('data', 'logs', 'coder_instruction.md')
    with open(instruction_path, 'w', encoding='utf-8') as f:
        f.write(coder_instruction)
        
    print(f"[+] 程序员指令已生成: {instruction_path}")
    return coder_instruction

if __name__ == '__main__':
    # 示例运行
    with open('data/logs/analysis_report.md', 'r', encoding='utf-8') as f:
        suggestions = f.read()
    apply_improvements(suggestions)
