from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BybitCategory = Literal["spot", "linear", "inverse"]
VALID_INTERVALS = frozenset({"1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"})


class KlineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: BybitCategory
    symbol: str = Field(min_length=2, max_length=30)
    interval: str
    limit: int = Field(ge=1, le=1000)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        if value != value.upper() or not value.isascii() or not value.isalnum():
            raise ValueError("symbol must be an uppercase exchange symbol")
        return value

    @field_validator("interval")
    @classmethod
    def valid_interval(cls, value: str) -> str:
        if value not in VALID_INTERVALS:
            raise ValueError("interval is not a valid Bybit interval")
        return value

    @model_validator(mode="after")
    def ordered_range(self) -> "KlineRequest":
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must be less than or equal to end")
        return self


class KlineResponse(BaseModel):
    request_id: str
    node_id: str
    exchange: Literal["bybit"]
    observed_at: datetime
    latency_ms: int = Field(ge=0)
    exchange_http_status: int = Field(ge=100, le=599)
    payload: dict
