# CodeAgent

独立实现的编程智能体：DeepSeek（OpenAI 兼容接口）+ 自研 ReAct 循环。不用 LangChain 等 agent 框架。

当前能力：多轮 CLI、流式输出、`@tool` 注册、文件工具、workspace 沙箱、Bash 三级权限、Todo/提问/Notebook 工具。

答辩/演示讲解见 [亮点.md](亮点.md)。

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

## 使用

```powershell
python -m codeagent
```

把要修改的代码放在 `workspace/` 下。Agent 只能在该目录内读写文件、执行 Bash（cwd 锁定为 workspace）。

## 工具一览

| 工具 | 作用 |
| --- | --- |
| `Read` / `Write` / `Edit` / `Glob` / `Grep` | 文件读写与搜索 |
| `NotebookEdit` | 编辑 Jupyter cell |
| `Bash` | 编译检查、运行程序（有权限控制） |
| `TodoWrite` | 会话内任务列表 |
| `AskUserQuestion` | 向用户提问（单选/多选/自由输入） |
| `test` | 连通性测试 |

## Bash 权限（deny > ask > allow）

对整条命令（及 `;` `&&` `||` `|` 拆开的每一段）按优先级判定：

| 级别 | 行为 | 示例 |
| --- | --- | --- |
| **deny** | 直接拒绝，不问用户 | `rm -rf`、`echo a > f.txt`、`cd ..`、`pip install`、改 `.env` |
| **ask** | 终端询问 `y/N` | `make`、`cmake`、未匹配白名单的命令 |
| **allow** | 直接执行 | `g++ hello.cpp`、`python hello.py`、`pytest`、`git status`、`dir` |

原则：**改文件必须用 Write/Edit/NotebookEdit，不要用 Bash。** Bash 只用于编译是否通过、程序跑起来是什么结果。

后台任务：`Bash(..., background=True)`，日志在 `workspace/.agent/jobs/<id>.log`，可用 Read 查看。

## 添加工具

用 `@registry.tool` 装饰器注册；文件路径经 `Workspace.resolve()`；Bash 类工具走 `bash_policy`。

## 目录

```text
codeagent/tools/
  bash_policy.py   deny/ask/allow 规则
  bash.py          Bash 执行
  interact.py      AskUserQuestion
  todo.py          TodoWrite
  notebook.py      NotebookEdit
  files.py         Read/Write/Edit/Glob/Grep
workspace/         默认活动范围
```
