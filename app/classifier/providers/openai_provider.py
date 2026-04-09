from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

from app.classifier.providers.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.name = f"openai:{self.model}"
        self._client = OpenAI()

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        # Strict JSON-schema structured outputs: the model literally cannot
        # emit tokens that would violate the schema (e.g. a 4th bucket).
        resp = self._client.chat.completions.create(
            model=self.model,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "Classification",
                    "schema": schema,
                    "strict": True,
                },
            },
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or "{}"
