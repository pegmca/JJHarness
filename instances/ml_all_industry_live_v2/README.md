# Harness Quant: All-Industry ML Strategy (ml_all_industry_v1)

这是一个最终调优完成的高性能机器学习选股策略，针对中证1000小盘股动量设计。

## 🏆 最终性能 (2025.11 - 2026.05)
*   **累计收益率:** **40.97%** (跑赢基准 27.6%)
*   **夏普比率:** **2.00**
*   **最大回撤:** 10.85%
*   **基准 (CSI 1000):** 13.37%

## 🛠️ 核心技术架构
1.  **模型:** LightGBM 回归模型，预测 2 日相对 Alpha 收益。
2.  **特征:** RSI Slope, Volume Spike, Skewness, Z-Score Price Position。
3.  **风控:** 
    *   **Position Buffer:** 只有新标的进入 Top 3 时才替换 Top 5 持仓，极低摩擦。
    *   **Vol Filter:** 市场年化波动率 > 45% 时自动清仓。
    *   **Stop Loss:** 8% 个股硬止损。

## 🚀 启动步骤
1. 修改 `src/strategy/base_strategy.py` 中的 `token` 和 `strategy_id`。
2. 修改 `context.symbol` 为你想要交易的股票代码。
3. 在当前目录下运行：

```powershell
gemini --yolo "根据最新的回测结果，自主优化策略参数并进行 5 轮迭代，目标是提高收益率。"
```

## 📂 环境配置
本实例共享根目录下的虚拟环境：`../../venv/Scripts/python.exe`
回测脚本 `src/strategy/backtest_runner.py` 已自动适配。
