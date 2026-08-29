# CodeAgent

独立实现的编程智能体：DeepSeek（OpenAI 兼容接口）+ 自研 ReAct 循环。不用 LangChain 等 agent 框架。

当前能力：多轮 CLI、流式输出、文件工具、Bash 权限、**两层上下文压缩 + 规则式 Memory**、**会话落盘与 Web 多窗口**。

答辩/演示讲解见 [亮点.md](亮点.md)。

## 上下文压缩与 Memory

- 预算默认 **1M token**（`CODEAGENT_CONTEXT_TOKENS`，对齐 DeepSeek V4）
- **≥70%**：第一层蒸馏全部工具输出（日志→状态句）
- 仍 **>35%**：第二层会话快照 + 更新三层记忆
- 仍 **>100%**：打印错误并退出，不发请求
- 工具失败会写成 `[error:…]` 观察（缺参、越界、超时）；连续 3 次同类失败会熔断
- 模型 API 超时/429 会重试；服务端报上下文过长会先强制快照再试一次
- **三层记忆**（压缩后写入 system）：
  - **会话**：`sessions/{id}.json` 的 `memory` 字段（本会话目标/进度）
  - **工作区**：`workspace/.agent/memory/short_term.txt` + `long_term.txt`（项目状态与约束）
  - **全局**：`.agent/memory/global.txt`（跨工作区偏好，可用 `CODEAGENT_GLOBAL_MEMORY_DIR` 覆盖）

测试压缩可把 `CODEAGENT_CONTEXT_TOKENS` 调小（如 `2000`）。

## 环境要求

- Python 3.11+
- DeepSeek API Key（[申请与文档](https://api-docs.deepseek.com/)）

## 配置指南

### 1. 虚拟环境与依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. API Key

```powershell
copy .env.example .env
```

编辑 `.env` 填写 `DEEPSEEK_API_KEY` 等。`workspace/` 不存在时会自动创建。

| 变量 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 必填 |
| `CODEAGENT_WORKSPACE` | 默认 `<项目根>/workspace/` |
| `CODEAGENT_MAX_TURNS` | 默认 `24` |
| `CODEAGENT_CONTEXT_TOKENS` | 上下文预算，默认 `1000000` |
| `CODEAGENT_SESSIONS_DIR` | 会话 JSON 目录，默认 `<项目根>/sessions/` |
| `CODEAGENT_GLOBAL_MEMORY_DIR` | 全局记忆目录，默认 `<项目根>/.agent/memory/` |
| `CODEAGENT_SUBAGENT_MAX_TURNS` | 子 Agent 单轮最大循环次数，默认 `8` |

## 使用

```powershell
python -m codeagent
```

启动 Web 界面（左侧会话栏 + 右侧流式对话，默认 `http://127.0.0.1:8765`）。会话窗口上方显示当前上下文 token（含工具 schema）与本会话累计用量（各轮请求估算之和）：

```powershell
python -m codeagent --web
```

恢复指定会话：

```powershell
python -m codeagent --resume <会话id>
```

CLI 内斜杠命令（不进模型）：

| 命令 | 作用 |
| --- | --- |
| `/new` | 新建并切换会话 |
| `/list` | 列出最近会话 |
| `/resume <id>` | 加载会话 |
| `/search <关键词>` | 按标题与对话内容检索 |
| `/web` | 提示使用 `--web` |

会话文件保存在仓库根目录 `sessions/`（`.gitignore` 为 `/sessions/`，只忽略数据目录，不会误伤 `codeagent/sessions/` 源码）。每轮回复后自动落盘；含 `messages`、`todos`、`memory` 以及 token 统计。工作区与全局记忆分别落在 `workspace/.agent/memory/` 与 `.agent/memory/`。

把要修改的代码放在 `workspace/` 下。Agent 只能在该目录内读写文件、执行 Bash（cwd 锁定为 workspace）。

## 工具一览

| 工具 | 作用 |
| --- | --- |
| `Read` / `Write` / `Edit` / `Glob` / `Grep` | 文件读写与搜索 |
| `NotebookEdit` | 编辑 Jupyter cell |
| `Bash` | 编译检查、运行程序（有权限控制） |
| `TodoWrite` | 会话内任务列表 |
| `AskUserQuestion` | 向用户提问（单选/多选/自由输入） |
| `Task` | 只读子 Agent（Glob/Grep/Read），探索后返回摘要；不可递归、不可改文件 |

## Bash 权限（deny > ask > allow）

对整条命令（及 `;` `&&` `||` `|` 拆开的每一段）按优先级判定：

| 级别 | 行为 | 示例 |
| --- | --- | --- |
| **deny** | 直接拒绝，不问用户 | `rm -rf`、`echo a > f.txt`、`cd ..`、`pip install`、改 `.env` |
| **ask** | 终端询问 `y/N` | `make`、`cmake`、未匹配白名单的命令 |
| **allow** | 直接执行 | `g++ hello.cpp`、`python hello.py`、`pytest`、`git status`、`dir` |

原则：**改文件走 Write/Edit/NotebookEdit，不要用 Bash 重定向或 rm/cp。** 策略看的是命令字符串，不是进程里的文件系统调用；白名单里的 `python xxx.py` 脚本内部仍可能写文件。Bash 主要用于编译是否通过、程序跑起来是什么结果。

后台任务：`Bash(..., background=True)`，日志在 `workspace/.agent/jobs/<id>.log`，可用 Read 查看。

## 添加工具

用 `@registry.tool` 装饰器注册；文件路径经 `Workspace.resolve()`；Bash 类工具走 `bash_policy`。

## 目录

```text
codeagent/context/   token 计数、两层压缩
codeagent/memory/    三层记忆（全局 / 工作区 / 会话）
codeagent/sessions/  会话落盘与恢复
codeagent/web/       本地 Web（http.server + 静态页）
codeagent/tools/     工具与 Bash 权限
workspace/           默认活动范围
sessions/            会话 JSON（gitignore）
```
