# Harness Quant: 多实例量化管理平台

本项目采用“共享环境，隔离实例”的架构。所有的策略实例都存放在 `instances/` 目录下，并共享根目录下的 Python 虚拟环境。

## 目录结构
- `venv/`: 共享的 Python 虚拟环境。
- `requirements.txt`: 全局依赖配置。
- `template/`: 标准化策略模板目录，用于快速初始化新实例。
- `instances/`: 存放独立的量化策略项目。

## 如何新增一个策略实例？
1. 在 `instances/` 下创建一个新文件夹（例如 `my_new_strategy`）。
2. 将 `template/` 下的所有文件和目录拷贝到新文件夹中。
3. 修改新实例中的 `src/strategy/base_strategy.py` 配置（Token, ID, Symbol）。
4. 进入该目录启动 `gemini` 即可开始新的隔离迭代。

## 核心准则
- **绝对隔离:** 严禁在一个实例的 AI 会话中读取另一个实例的文件。
- **共享环境:** 始终使用根目录的 `venv` 运行回测，确保库版本一致。
