# Harness Quant: Daily ML Short-term Strategy (ml_daily_short_v1)

这是一个基于机器学习（LightGBM）的每日调仓短线策略，专门针对中证1000小盘股设计。

## 🌟 核心特性
*   **高频调仓:** 每日重新计算模型评分，动态调整持仓。
*   **智能缓冲:** 引入 Position Buffer 机制，只有新机会足够强（进入前3）时才触发换仓，极大缓解了每日调仓的滑点损耗。
*   **截面预测:** 预测股票相对于市场中位数的 Alpha 收益，而非绝对价格，更具稳定性。
*   **双重风控:** 分钟级实时止损 + 市场波动率阈值过滤。

## 🚀 快速开始
1. 确保已安装 `lightgbm` 库。
2. 运行回测：
```powershell
# 在实例目录下执行
gemini --yolo "运行完整回测并生成分析报告。"
```

## 📂 结构说明
*   `src/strategy/base_strategy.py`: 策略核心代码。
*   `src/agent/`: 包含 Analyst, Coder, Detector 等自动化代理。
*   `docs/`: 包含详细设计方案和路线图。
