from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Minimal interface: take a system + user prompt + a JSON schema,
    return JSON text that conforms to the schema."""

    name: str

    @abstractmethod
    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        """Return a JSON string that conforms to `schema`."""
