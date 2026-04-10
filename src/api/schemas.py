from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchResultModel(BaseModel):
    product_id: str
    product_locale: str
    product_title: str
    product_brand: str
    product_color: str
    score: float
    rank: int
    searchable_text: str
    raw_scores: dict[str, float] = Field(default_factory=dict)
    debug_details: dict[str, Any] = Field(default_factory=dict)


class SearchResponseModel(BaseModel):
    query: str
    requested_mode: str
    used_mode: str
    locale: str
    results: list[SearchResultModel]
    timings_ms: dict[str, float]
    request_id: str
    fallback_triggered: bool = False
    fallback_reason: str | None = None


class HealthResponseModel(BaseModel):
    status: str
    profile: str
    services: dict[str, Any]


class ExplainResponseModel(BaseModel):
    payload: dict[str, Any]
