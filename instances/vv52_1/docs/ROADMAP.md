# 项目路线图 (ROADMAP)

## 阶段 1: 基础设施搭建 (当前阶段)
- [x] 1.1 初始化 Python 环境，安装掘金量化 SDK (`gm`) 及依赖。
- [x] 1.2 编写一个最简单的掘金双均线策略 (`src/strategy/base_strategy.py`) 作为迭代起点。
- [x] 1.3 编写回测自动化脚本 (`src/strategy/backtest_runner.py`)，能通过命令行触发，并输出可供机器读取的结果。

## 阶段 2: AI Agent 构建
- [x] 2.1 编写 `coder.py`: 实现对策略文件的读取、使用 LLM API (如 Gemini/OpenAI) 生成新代码并覆盖保存。
- [x] 2.2 编写 `analyst.py`: 解析 `backtest_runner.py` 的输出，评估夏普比率和回撤，生成优化 Prompts。
- [x] 2.3 编写 `detector.py`: 建立未来函数扫描机制，在回测前进行合规性审计。

## 阶段 3: Ralph 闭环集成
- [x] 3.1 编写主循环控制脚本 `ralph_loop.py`，并将 `detector.py` 的审计结果作为回测准入条件。
- [x] 3.2 进行首次全自动闭环测试（设定迭代上限 5 次），观察系统能否自主提升初始双均线策略的收益。
- [x] 3.3 扩展数据维度：让 LLM 意识到可以同时订阅 Tick 和分钟数据，并优化出跨周期的策略代码。
