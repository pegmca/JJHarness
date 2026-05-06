# Harness Quant: LLM 自主量化系统

这是一个集成了 **掘金量化 (MyQuant)** 和 **Gemini AI** 的自主迭代系统。它能够自动编写策略、执行回测、分析结果并根据反馈不断优化代码。

## 🚀 快速启动（继续迭代）

如果你关闭了会话并想重新开始自动迭代，请在项目根目录下运行以下命令：

```powershell
gemini --yolo "根据最新的回测结果，自主优化策略参数并进行 30 轮迭代，目标是提高收益率。"
```

## 📂 项目结构

- `src/strategy/base_strategy.py`: **当前最优策略代码**。
- `src/strategy/backtest_runner.py`: 自动化回测引擎。
- `src/agent/`: AI 分析师与程序员的逻辑脚本。
- `docs/ROADMAP.md`: 详细的任务进度表。
- `docs/DETAILED_DESIGN.md`: 系统架构与设计文档。
- `GEMINI.md`: AI 的核心指令与工作规范。

## 🛠️ 环境要求

1. 确保已安装 Python 并激活了环境。
2. 确保掘金量化终端已打开并登录。
3. 依赖安装：`pip install -r requirements.txt`

## 📈 数据权限提醒

系统已内置权限感知逻辑：
- **分钟线:** 2025-11-02 至今。
- **Tick:** 2026-04-24 至今。
- 回测时请确保时间跨度在授权范围内。
