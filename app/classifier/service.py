from __future__ import annotations

import json
import os
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.classifier.prompt import SYSTEM_PROMPT, build_user_prompt
from app.classifier.providers.base import LLMProvider
from app.models import Track

Bucket = Literal["likely_owned", "likely_available", "unclear"]


class LLMResponse(BaseModel):
    """The inner contract the LLM is responsible for. Used as the strict
    JSON schema for OpenAI structured outputs so a 4th bucket is impossible
    at decode time, not just rejected at parse time."""

    bucket: Bucket
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

    model_config = {"extra": "forbid"}


class Classification(BaseModel):
    isrc: str
    bucket: Bucket
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence: dict
    model: str


def get_default_provider() -> LLMProvider:
    name = os.getenv("LLM_PROVIDER", "openai").lower()
    if name == "openai":
        from app.classifier.providers.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if name == "anthropic":
        from app.classifier.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {name}")


def _serialize_track(track: Track) -> dict:
    return {
        "title": track.title,
        "artist": track.artist,
        "imprint": track.imprint,
        "release_date": track.release_date.isoformat() if track.release_date else None,
    }


def _serialize_cid(track: Track) -> dict | None:
    if not track.cid:
        return None
    return {
        "asset_id": track.cid.asset_id,
        "label": track.cid.label,
        "owner": track.cid.owner,
        "asset_type": track.cid.asset_type,
        "artists": track.cid.artists,
    }


class ClassifierService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_default_provider()

    def classify(self, track: Track) -> Classification:
        track_payload = _serialize_track(track)
        cid_payload = _serialize_cid(track)
        evidence = {"track": track_payload, "cid": cid_payload}

        user = build_user_prompt(track.isrc, track_payload, cid_payload)
        schema = LLMResponse.model_json_schema()
        # OpenAI strict mode requires additionalProperties:false at every level.
        schema["additionalProperties"] = False
        raw = self.provider.complete_json(SYSTEM_PROMPT, user, schema)

        try:
            inner = LLMResponse.model_validate_json(raw)
        except (json.JSONDecodeError, ValidationError) as e:
            raise ValueError(f"Provider returned malformed classification: {raw!r}") from e

        return Classification(
            isrc=track.isrc,
            bucket=inner.bucket,
            confidence=inner.confidence,
            reasoning=inner.reasoning,
            evidence=evidence,
            model=self.provider.name,
        )
