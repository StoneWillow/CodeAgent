from __future__ import annotations

from pathlib import Path


class Workspace:
    """Sandbox: all file tool paths must resolve inside this root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, user_path: str) -> Path | str:
        """Return resolved Path inside root, or an error message string."""
        if not user_path or not str(user_path).strip():
            return "错误：路径不能为空。"

        raw = Path(user_path)
        candidate = (self.root / raw).resolve() if not raw.is_absolute() else raw.resolve()

        try:
            candidate.relative_to(self.root)
        except ValueError:
            return (
                f"错误：路径越界，只能访问工作区内的文件。"
                f"工作区: {self.root}"
            )

        return candidate

    def relative_display(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()
