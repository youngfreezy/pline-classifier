from __future__ import annotations

import json
import os
from typing import Any

from app.classifier.providers.base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Anthropic provider using tool-use for typed structured output.

    The model is forced to call a single `emit_classification` tool whose
    input_schema is the Classification JSON schema, so the bucket field is
    constrained at decode time the same way OpenAI's structured outputs
    enforce it.
    """

    def __init__(self, model: str | None = None) -> None:
        from anthropic import Anthropic

        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self.name = f"anthropic:{self.model}"
        self._client = Anthropic()

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            temperature=0,
            tools=[
                {
                    "name": "emit_classification",
                    "description": "Emit the ownership classification for the track.",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": "emit_classification"},
            messages=[{"role": "user", "content": user}],
        )
        for block in msg.content:
            if block.type == "tool_use":
                return json.dumps(block.input)
        return "{}"
