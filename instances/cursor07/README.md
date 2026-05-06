# Harness Quant: [新策略实例名称]

这是一个基于 Harness Quant 模板创建的隔离策略实例。

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
