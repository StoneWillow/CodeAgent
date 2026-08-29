# CodeAgent

独立实现的编程智能体：DeepSeek（OpenAI 兼容接口）+ 自研 ReAct 循环。不用 LangChain 等 agent 框架。

当前为第一层：多轮 CLI、内存上下文、可注册工具。内置最小工具 `test`（调用时返回「你调用了工具」）。

## 环境要求

- Python 3.11+
- DeepSeek API Key（[申请与文档](https://api-docs.deepseek.com/)）

## 配置指南

### 1. 虚拟环境与依赖

在项目根目录：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

若访问官方 PyPI 出现 SSL 错误，可用清华镜像：

```powershell
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
```

Cursor 请将解释器选为 `.venv\Scripts\python.exe`。

### 2. API Key（必须）

密钥只放在 `.env`，不要写进仓库、README 或 `.env.example`。

```powershell
copy .env.example .env
```

编辑 `.env`，至少填写：

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
CODEAGENT_MAX_TURNS=8
```

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 是 | DeepSeek 密钥；也可用 `LLM_API_KEY` |
| `LLM_PROVIDER` | 否 | 默认 `deepseek` |
| `DEEPSEEK_BASE_URL` | 否 | 默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 否 | 默认 `deepseek-v4-flash`，可改为 `deepseek-v4-pro` |
| `CODEAGENT_MAX_TURNS` | 否 | 单次用户输入内「模型 ↔ 工具」最大轮数，默认 `8` |
| `CODEAGENT_WORKSPACE` | 否 | 工作区根目录，默认当前工作目录（给后续文件工具用） |

程序启动时会读取项目根目录的 `.env`。改完配置后重新启动 CLI 才会生效。

## 使用指南

在项目根目录、已激活虚拟环境的前提下：

```powershell
python -m codeagent
```

进入同一会话的多轮对话。输入 `exit` / `quit` 退出（`Ctrl+C` 同样退出）。

把第一句话写在命令行里也可以，之后仍停留在多轮：

```powershell
python -m codeagent 请调用 test 工具
```

### 对话时会发生什么

1. 你的输入写入当前会话的消息历史。
2. Agent 调用模型；若模型发出 `tool_calls`，本地执行工具，把结果写回历史，再让模型继续，直到给出对用户的文本回复，或达到 `CODEAGENT_MAX_TURNS`。
3. 下一轮提问仍使用同一段历史（第一层不切换会话、不落盘）。

调用 `test` 时终端会先打印工具行，例如：

```text
你> 请调用 test 工具
  [工具] test({})
Agent> ……
```

工具本身固定返回：`你调用了工具`。

### 常见问题

- **提示缺少 API key**：确认项目根目录存在 `.env`（不是只改了 `.env.example`），且 `DEEPSEEK_API_KEY` 非空。
- **中文乱码**：使用 Windows Terminal / 新版 PowerShell，并保证以 UTF-8 输出。
- **想换更强模型**：在 `.env` 把 `DEEPSEEK_MODEL` 改为 `deepseek-v4-pro`。

## 添加工具

新工具继承 `codeagent.tools.base.Tool`，实现 `execute`，再在 `codeagent.tools.build_default_registry` 里 `register`。不必改 ReAct 循环。

```python
from codeagent.tools.base import Tool

class PingTool(Tool):
    name = "ping"
    description = "连通性探测。无需参数。"
    parameters = {"type": "object", "properties": {}}

    def execute(self, arguments: dict) -> str:
        return "pong"
```

然后在 `build_default_registry()` 中：`registry.register(PingTool())`。

## 目录（第一层）

```text
codeagent/
  llm/          各模型客户端（OpenAI 兼容）
  prompts/      系统提示词（后续升级为 memory）
  tools/        工具基类、注册表、test 工具
  agent.py      ReAct 循环
  conversation.py  内存消息列表
  cli.py        多轮 CLI
  config.py     读取 .env
```
