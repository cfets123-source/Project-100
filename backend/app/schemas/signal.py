"""
Strict schema for anything crossing the Strategy/AI -> Risk Engine boundary.
extra='forbid' means unknown fields (e.g. an injected 'override_risk': true from
an LLM or news payload) cause validation to fail closed, not silently pass through.
"""
from pydantic import BaseModel, ConfigDict, field_validator


class SignalSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    direction: str          # long|short
    strategy: str
    entry_price: float
    stop_price: float
    target_price: float | None = None
    thesis: str | None = None
    ai_confidence: float | None = None

    @field_validator("direction")
    @classmethod
    def _direction_valid(cls, v):
        if v not in ("long", "short"):
            raise ValueError("direction must be 'long' or 'short'")
        return v

    @field_validator("ai_confidence")
    @classmethod
    def _confidence_bounded(cls, v):
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("ai_confidence must be in [0,1]")
        return v
