from __future__ import annotations


class ContextOverflowError(Exception):
    def __init__(self, used: int, budget: int) -> None:
        self.used = used
        self.budget = budget
        super().__init__(f"上下文超过上限 ({used}/{budget} token)")
