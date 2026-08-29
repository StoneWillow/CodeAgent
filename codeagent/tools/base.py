from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """One local tool. Subclass, then register on ToolRegistry."""

    name: str
    description: str
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
    }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> str:
        """Return a string observation for the model."""
