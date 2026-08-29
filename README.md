# CodeAgent

独立实现的编程智能体：DeepSeek（OpenAI 兼容接口）+ 自研 ReAct 循环。不用 LangChain 等 agent 框架。

当前为第二层：多轮 CLI、流式输出、内存上下文、`@tool` 注册、文件工具与 workspace 沙箱。

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
CODEAGENT_MAX_TURNS=24
```

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 是 | DeepSeek 密钥；也可用 `LLM_API_KEY` |
| `LLM_PROVIDER` | 否 | 默认 `deepseek` |
| `DEEPSEEK_BASE_URL` | 否 | 默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 否 | 默认 `deepseek-v4-flash`，可改为 `deepseek-v4-pro` |
| `CODEAGENT_MAX_TURNS` | 否 | 单次用户输入内「模型 ↔ 工具」最大轮数，默认 `24` |
| `CODEAGENT_WORKSPACE` | 否 | 文件工具活动范围，默认项目根目录下的 `workspace/` |

程序启动时会读取项目根目录的 `.env`。`workspace/` 不存在时会自动创建。改完配置后重新启动 CLI 才会生效。

## 使用指南

在项目根目录、已激活虚拟环境的前提下：

```powershell
python -m codeagent
```

进入同一会话的多轮对话。模型回复会按 token 流式打印到终端。输入 `exit` / `quit` 退出（`Ctrl+C` 同样退出）。

把第一句话写在命令行里也可以，之后仍停留在多轮：

```powershell
python -m codeagent 在 workspace 里创建一个 hello.py
```

### 活动范围（workspace）

所有文件工具的读写都限制在 workspace 内：

- 默认目录：`<项目根>/workspace/`
- 可用 `CODEAGENT_WORKSPACE` 覆盖
- 访问 `../.env`、项目外绝对路径等会被拒绝

请把要交给 Agent 修改的代码放在 `workspace/` 下。

### 文件工具

| 工具 | 作用 |
| --- | --- |
| `Read` | 读取文本、`.ipynb`、`.pdf`（抽文本）；不支持图片 |
| `Write` | 完整覆盖写入，适合新建文件 |
| `Edit` | 精确替换，适合小范围修改 |
| `Glob` | 按模式搜索文件路径（如 `**/*.py`） |
| `Grep` | 在文件内容中按正则搜索 |
| `test` | 连通性测试，返回「你调用了工具」 |

### 对话时会发生什么

1. 你的输入写入当前会话的消息历史。
2. Agent 调用模型；若模型发出 `tool_calls`，在 workspace 内本地执行，把结果写回历史，再让模型继续，直到给出对用户的文本回复，或达到 `CODEAGENT_MAX_TURNS`。
3. 下一轮提问仍使用同一段历史（当前不落盘）。

### 常见问题

- **提示缺少 API key**：确认项目根目录存在 `.env`（不是只改了 `.env.example`），且 `DEEPSEEK_API_KEY` 非空。
- **中文乱码**：使用 Windows Terminal / 新版 PowerShell，并保证以 UTF-8 输出。
- **想换更强模型**：在 `.env` 把 `DEEPSEEK_MODEL` 改为 `deepseek-v4-pro`。
- **路径越界**：检查路径是否相对 `workspace/`，不要用 `..` 逃出沙箱。

## 添加工具

推荐用 `@registry.tool` 装饰器（类似 `@tool`），从函数签名自动生成 schema：

```python
from pathlib import Path
from codeagent.tools import ToolRegistry
from codeagent.tools.workspace import Workspace

def build_my_registry(workspace: Path) -> ToolRegistry:
    ws = Workspace(workspace)
    registry = ToolRegistry()

    @registry.tool
    def ping() -> str:
        """连通性探测。无需参数。"""
        return "pong"

    return registry
```

文件类工具的路径必须经过 `Workspace.resolve()`，不要直接 `open()` 用户传入的路径。

## 目录

```text
codeagent/
  llm/          各模型客户端（OpenAI 兼容）
  prompts/      系统提示词（后续升级为 memory）
  tools/        @tool 注册、workspace 沙箱、文件工具
  agent.py      ReAct 循环
  conversation.py  内存消息列表
  cli.py        多轮 CLI
  config.py     读取 .env
workspace/      Agent 默认活动范围（可放演示项目）
```
