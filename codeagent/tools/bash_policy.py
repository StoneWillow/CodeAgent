from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PermissionDecision(str, Enum):
    DENY = "deny"
    ASK = "ask"
    ALLOW = "allow"


@dataclass(frozen=True)
class PermissionResult:
    decision: PermissionDecision
    reason: str
    segment: str | None = None


_SEGMENT_SPLIT = re.compile(r"\s*(?:;|&&|\|\|)\s*|\s*\|\s*")

# --- deny patterns (highest priority) ---
_DENY_PATTERNS: list[tuple[str, str]] = [
    (r"[>]{1,2}", "禁止 shell 重定向写文件，请使用 Write/Edit 工具"),
    (r"\btee\b", "禁止 tee 写文件，请使用 Write/Edit 工具"),
    (r"\b(Set-Content|Out-File|Add-Content)\b", "禁止 PowerShell 写文件，请使用 Write/Edit 工具"),
    (r"\b(rm|rmdir|del|erase|rd|Remove-Item|ri)\b", "禁止删除文件，请使用专用工具"),
    (r"\brm\s+-rf\b", "禁止 rm -rf"),
    (r"\bshred\b", "禁止 shred"),
    (r"\b(mv|move|cp|copy|Copy-Item|Move-Item|ren|rename)\b", "禁止移动/复制/重命名，请使用 Write/Edit"),
    (r"\b(mkdir|md|New-Item|ni|touch)\b", "禁止创建目录/文件，请使用 Write"),
    (r"\b(chmod|chown|icacls|takeown|attrib)\b", "禁止修改权限/属主"),
    (r"\b(sudo|runas)\b", "禁止提权"),
    (r"Start-Process\s+.*-Verb\s+RunAs", "禁止提权"),
    (r"\b(format|diskpart|mkfs|cipher\s+/w)\b", "禁止磁盘破坏命令"),
    (r"\bdd\s+if=", "禁止 dd"),
    (r"\b(Invoke-Expression|iex)\b", "禁止 Invoke-Expression"),
    (r"\b(Invoke-WebRequest|iwr|curl|wget|bitsadmin)\b", "禁止网络下载命令"),
    (r"\|\s*(sh|bash|powershell|pwsh|cmd)\b", "禁止管道执行脚本"),
    (r"-enc(odedcommand)?\b", "禁止编码命令"),
    (r"\bcmd\s+/c\b", "禁止 cmd /c 嵌套"),
    (r"\bgit\s+(push|reset|clean|rebase|commit|add)\b", "禁止破坏性 git 写操作"),
    (r"\bgit\s+checkout\s+--", "禁止 git checkout --"),
    (r"\b(pip|npm)\s+(install|uninstall)\b", "禁止包管理安装/卸载"),
    (r"\bnpx\b", "禁止 npx"),
    (r"\b(cd|Set-Location|pushd)\s+(\.\.|/|~|[A-Za-z]:\\|[A-Za-z]:/)", "禁止 cd 逃出 workspace"),
    (r"\.\./", "禁止访问上级目录"),
    (r"(\.env|codeagent[/\\]|\.git[/\\])", "禁止触及 agent 自身或 git 元数据"),
    (r"\b(nohup|Start-Process)\b", "禁止独立后台启动，请使用 Bash 的 background 参数"),
    (r"\bstart\s+", "禁止 start 后台启动"),
]

# --- allow patterns (lowest priority, only if no deny) ---
_ALLOW_PATTERNS: list[tuple[str, str]] = [
    (r"^\s*(g\+\+|gcc|clang\+\+?|javac|rustc)(?:\s|$)", "编译器检查"),
    (r"^\s*go\s+build\b", "Go 编译"),
    (r"^\s*python\s+-m\s+(py_compile|compileall|pytest|unittest)\b", "Python 检查/测试"),
    (r"^\s*py\s+-m\s+(py_compile|compileall|pytest|unittest)\b", "Python 检查/测试"),
    (r"^\s*(python|py)\s+[\w./\\-]+\.(py|pyw)\b", "运行 Python 脚本"),
    (r"^\s*node\s+[\w./\\-]+\.(js|mjs|cjs)\b", "运行 Node 脚本"),
    (r"^\s*go\s+run\b", "Go 运行"),
    (r"^\s*java\s+", "运行 Java"),
    (r"^\s*(\./|\.\/)[\w./\\-]+\b", "运行本地可执行文件"),
    (r"^\s*[\w./\\-]+\.(exe|out)\b", "运行可执行文件"),
    (r"^\s*pytest\b", "pytest"),
    (r"^\s*(ls|dir|pwd|Get-Location|whoami|where|which)\b", "只读查看"),
    (r"^\s*(type|cat|head|tail)\s+", "只读查看文件"),
    (r"^\s*git\s+(status|log|diff|branch)\b", "只读 git"),
]

# --- ask patterns (explicit ask before fallback) ---
_ASK_PATTERNS: list[tuple[str, str]] = [
    (r"^\s*(make|cmake)\b", "构建系统可能写入产物"),
    (r"^\s*cargo\s+(build|test|run)\b", "Cargo 可能写入 target/"),
    (r"^\s*msbuild\b", "MSBuild 构建"),
]


def _split_segments(command: str) -> list[str]:
    parts = _SEGMENT_SPLIT.split(command.strip())
    return [p.strip() for p in parts if p.strip()]


def _match_patterns(segment: str, patterns: list[tuple[str, str]]) -> str | None:
    for pattern, reason in patterns:
        if re.search(pattern, segment, re.IGNORECASE):
            return reason
    return None


def _check_absolute_escape(segment: str, workspace: Path) -> str | None:
    """Reject absolute paths outside workspace when detectable."""
    for match in re.finditer(r"[A-Za-z]:[\\/][^\s\"'|;&]+", segment):
        candidate = Path(match.group(0))
        try:
            resolved = candidate.resolve()
            resolved.relative_to(workspace.resolve())
        except (ValueError, OSError):
            return f"绝对路径越界: {match.group(0)}"
    return None


def evaluate_command(command: str, workspace: Path) -> PermissionResult:
    if not command or not command.strip():
        return PermissionResult(PermissionDecision.DENY, "命令不能为空")

    segments = _split_segments(command)
    if not segments:
        return PermissionResult(PermissionDecision.DENY, "命令不能为空")

    for segment in segments:
        escape = _check_absolute_escape(segment, workspace)
        if escape:
            return PermissionResult(PermissionDecision.DENY, escape, segment)

        deny = _match_patterns(segment, _DENY_PATTERNS)
        if deny:
            return PermissionResult(PermissionDecision.DENY, deny, segment)

    allow_hits: list[str] = []
    ask_hits: list[str] = []

    for segment in segments:
        allow = _match_patterns(segment, _ALLOW_PATTERNS)
        if allow:
            allow_hits.append(allow)
            continue
        ask = _match_patterns(segment, _ASK_PATTERNS)
        if ask:
            ask_hits.append(ask)

    if len(allow_hits) == len(segments):
        return PermissionResult(
            PermissionDecision.ALLOW,
            "；".join(allow_hits),
        )

    if ask_hits:
        return PermissionResult(
            PermissionDecision.ASK,
            "；".join(ask_hits),
        )

    return PermissionResult(
        PermissionDecision.ASK,
        "未匹配白名单，需要用户确认",
    )
