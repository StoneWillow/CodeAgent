from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

from codeagent.tools.registry import ToolRegistry
from codeagent.tools.workspace import Workspace

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tiff", ".tif"}
_MAX_READ_CHARS = 100_000
_MAX_GLOB_RESULTS = 200
_MAX_GREP_MATCHES = 200
_BINARY_SAMPLE = 8192


def _is_probably_binary(data: bytes) -> bool:
    if b"\x00" in data[:_BINARY_SAMPLE]:
        return True
    if not data:
        return False
    text_chars = sum(1 for b in data[:_BINARY_SAMPLE] if 32 <= b < 127 or b in (9, 10, 13))
    return text_chars / min(len(data), _BINARY_SAMPLE) < 0.7


def _format_numbered_lines(lines: list[str], start_line: int = 1) -> str:
    width = max(len(str(start_line + len(lines) - 1)), 1)
    return "\n".join(
        f"{i:>{width}}|{line}" for i, line in enumerate(lines, start=start_line)
    )


def _read_ipynb(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    cells = data.get("cells") or []
    parts: list[str] = []
    for idx, cell in enumerate(cells, start=1):
        cell_type = cell.get("cell_type", "unknown")
        source = cell.get("source") or []
        if isinstance(source, list):
            text = "".join(source)
        else:
            text = str(source)
        parts.append(f"--- Cell {idx} ({cell_type}) ---\n{text.rstrip()}")
    return "\n\n".join(parts) if parts else "(空 notebook)"


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "错误：未安装 pypdf，无法读取 PDF。"
    reader = PdfReader(str(path))
    pages: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"--- Page {i} ---\n{text.rstrip()}")
    return "\n\n".join(pages) if pages else "(PDF 无文本内容)"


def register_file_tools(registry: ToolRegistry, ws: Workspace) -> None:
    @registry.tool
    def Read(path: str, offset: int = 1, limit: int | None = None) -> str:
        """读取工作区内文件。文本按行号返回；支持 .ipynb 与 .pdf 文本抽取。不支持图片。"""
        resolved = ws.resolve(path)
        if isinstance(resolved, str):
            return resolved
        if not resolved.exists():
            return f"错误：文件不存在: {ws.relative_display(resolved)}"
        if resolved.is_dir():
            return f"错误：路径是目录，不是文件: {ws.relative_display(resolved)}"

        suffix = resolved.suffix.lower()
        if suffix in _IMAGE_SUFFIXES:
            return (
                f"错误：不支持读取图片文件 ({suffix})。"
                f"路径: {ws.relative_display(resolved)}"
            )

        if suffix == ".ipynb":
            try:
                content = _read_ipynb(resolved)
            except (json.JSONDecodeError, OSError) as exc:
                return f"错误：读取 notebook 失败: {exc}"
        elif suffix == ".pdf":
            try:
                content = _read_pdf(resolved)
            except Exception as exc:
                return f"错误：读取 PDF 失败: {exc}"
        else:
            try:
                raw = resolved.read_bytes()
            except OSError as exc:
                return f"错误：读取文件失败: {exc}"
            if _is_probably_binary(raw):
                return (
                    f"错误：不支持读取二进制文件。"
                    f"路径: {ws.relative_display(resolved)}"
                )
            content = raw.decode("utf-8", errors="replace")

        lines = content.splitlines()
        start = max(1, offset)
        if start > len(lines) and lines:
            return f"错误：offset={start} 超出文件行数 ({len(lines)})。"

        if limit is None:
            selected = lines[start - 1 :]
            numbered = _format_numbered_lines(selected, start_line=start)
        else:
            end = start - 1 + max(0, limit)
            selected = lines[start - 1 : end]
            numbered = _format_numbered_lines(selected, start_line=start)

        if len(numbered) > _MAX_READ_CHARS:
            shown = numbered[:_MAX_READ_CHARS]
            return (
                f"{shown}\n\n"
                f"(输出已截断，共 {len(lines)} 行。"
                f"请增大 offset 继续读取。)"
            )
        return numbered if numbered else "(空文件)"

    @registry.tool
    def Write(path: str, contents: str) -> str:
        """写入工作区内文件，完整覆盖。适合新建文件或整文件重写。"""
        resolved = ws.resolve(path)
        if isinstance(resolved, str):
            return resolved
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(contents, encoding="utf-8", newline="\n")
        except OSError as exc:
            return f"错误：写入失败: {exc}"
        return f"已写入 {ws.relative_display(resolved)} ({len(contents)} 字符)"

    @registry.tool
    def Edit(
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        """精确替换文件内容。默认只替换唯一一处；多处匹配时需 replace_all=true。"""
        resolved = ws.resolve(path)
        if isinstance(resolved, str):
            return resolved
        if not resolved.exists():
            return f"错误：文件不存在: {ws.relative_display(resolved)}"
        if resolved.is_dir():
            return f"错误：路径是目录: {ws.relative_display(resolved)}"

        try:
            text = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            return f"错误：读取失败: {exc}"

        count = text.count(old_string)
        if count == 0:
            return f"错误：未找到要替换的文本。文件: {ws.relative_display(resolved)}"
        if count > 1 and not replace_all:
            return (
                f"错误：old_string 在文件中出现 {count} 次。"
                f"请提供更精确的上下文，或设置 replace_all=true。"
            )

        if replace_all:
            updated = text.replace(old_string, new_string)
            replaced = count
        else:
            updated = text.replace(old_string, new_string, 1)
            replaced = 1

        try:
            resolved.write_text(updated, encoding="utf-8", newline="\n")
        except OSError as exc:
            return f"错误：写入失败: {exc}"
        return f"已编辑 {ws.relative_display(resolved)}，替换 {replaced} 处。"

    @registry.tool
    def Glob(pattern: str, path: str = ".") -> str:
        """按 glob 模式搜索工作区内文件路径，如 **/*.py。"""
        base = ws.resolve(path)
        if isinstance(base, str):
            return base
        if not base.exists():
            return f"错误：目录不存在: {path}"
        if not base.is_dir():
            return f"错误：不是目录: {path}"

        matches: list[Path] = []
        for item in base.glob(pattern):
            if item.is_file():
                matches.append(item)

        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            return f"(无匹配: pattern={pattern!r}, path={path!r})"

        truncated = matches[:_MAX_GLOB_RESULTS]
        lines = [ws.relative_display(p) for p in truncated]
        header = f"找到 {len(matches)} 个文件"
        if len(matches) > len(truncated):
            header += f"（显示最新 {len(truncated)} 个）"
        return header + ":\n" + "\n".join(lines)

    @registry.tool
    def Grep(
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        case_insensitive: bool = False,
    ) -> str:
        """在工作区文件内容中按正则搜索。"""
        target = ws.resolve(path)
        if isinstance(target, str):
            return target

        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as exc:
            return f"错误：无效正则: {exc}"

        files: list[Path] = []
        if target.is_file():
            files = [target]
        elif target.is_dir():
            for item in target.rglob("*"):
                if not item.is_file():
                    continue
                if glob and not fnmatch.fnmatch(item.name, glob):
                    continue
                files.append(item)
        else:
            return f"错误：路径不存在: {path}"

        hits: list[str] = []
        for file_path in files:
            try:
                raw = file_path.read_bytes()
            except OSError:
                continue
            if _is_probably_binary(raw):
                continue
            text = raw.decode("utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    rel = ws.relative_display(file_path)
                    hits.append(f"{rel}:{line_no}:{line}")
                    if len(hits) >= _MAX_GREP_MATCHES:
                        return (
                            f"找到至少 {_MAX_GREP_MATCHES} 处匹配（已截断）:\n"
                            + "\n".join(hits)
                        )

        if not hits:
            return f"(无匹配: pattern={pattern!r})"
        return f"找到 {len(hits)} 处匹配:\n" + "\n".join(hits)
