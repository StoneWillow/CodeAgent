from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Callable

from codeagent.tools.bash_policy import PermissionDecision, evaluate_command
from codeagent.tools.registry import ToolRegistry
from codeagent.tools.workspace import Workspace

ConfirmBash = Callable[[str, str], bool]
_MAX_OUTPUT = 50_000
_MAX_TIMEOUT = 120
_DEFAULT_TIMEOUT = 30


def _truncate(text: str) -> str:
    if len(text) <= _MAX_OUTPUT:
        return text
    return text[:_MAX_OUTPUT] + f"\n...(输出已截断，共 {len(text)} 字符)"


def _format_result(stdout: str, stderr: str, exit_code: int) -> str:
    parts: list[str] = [f"exit_code={exit_code}"]
    if stdout:
        parts.append(f"stdout:\n{_truncate(stdout)}")
    if stderr:
        parts.append(f"stderr:\n{_truncate(stderr)}")
    if not stdout and not stderr:
        parts.append("(无输出)")
    return "\n".join(parts)


def register_bash_tool(
    registry: ToolRegistry,
    ws: Workspace,
    confirm_bash: ConfirmBash | None = None,
) -> None:
    jobs_dir = ws.root / ".agent" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    def _confirm(command: str, reason: str) -> bool:
        if confirm_bash is None:
            return False
        return confirm_bash(command, reason)

    @registry.tool
    def Bash(command: str, timeout: int = _DEFAULT_TIMEOUT, background: bool = False) -> str:
        """在工作区内执行 Shell 命令。仅用于编译检查与试运行；禁止用 Bash 增删改文件。"""
        timeout = max(1, min(int(timeout), _MAX_TIMEOUT))
        perm = evaluate_command(command, ws.root)

        if perm.decision is PermissionDecision.DENY:
            return (
                f"拒绝执行: {perm.reason}"
                f"{f' (片段: {perm.segment})' if perm.segment else ''}\n"
                "请使用 Write/Edit/NotebookEdit 修改文件，不要用 Bash。"
            )

        if perm.decision is PermissionDecision.ASK:
            if not _confirm(command, perm.reason):
                return f"用户拒绝执行: {perm.reason}\n命令: {command}"

        if background:
            job_id = uuid.uuid4().hex[:8]
            log_path = jobs_dir / f"{job_id}.log"
            with log_path.open("w", encoding="utf-8") as log_file:
                proc = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=str(ws.root),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            rel = ws.relative_display(log_path)
            return (
                f"后台任务已启动 job_id={job_id} pid={proc.pid}\n"
                f"日志: {rel}（可用 Read 查看）"
            )

        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=str(ws.root),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return f"错误：命令超时 ({timeout}s): {command}"
        except OSError as exc:
            return f"错误：执行失败: {exc}"

        return _format_result(
            completed.stdout or "",
            completed.stderr or "",
            completed.returncode,
        )
