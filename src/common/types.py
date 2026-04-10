from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchRequest:
    query: str
    mode: str = "bm25"
    brand: str | None = None
    color: str | None = None
    locale: str = "us"
    k: int = 10


@dataclass(frozen=True)
class SearchResult:
    product_id: str
    product_locale: str
    product_title: str
    product_brand: str
    product_color: str
    score: float
    rank: int
    searchable_text: str
    raw_scores: dict[str, float] = field(default_factory=dict)
    debug_details: dict[str, Any] = field(default_factory=dict)
    product_description: str = field(default="", repr=False, compare=False)
    product_bullet_point: str = field(default="", repr=False, compare=False)
    product_text: str = field(default="", repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("product_description", None)
        payload.pop("product_bullet_point", None)
        payload.pop("product_text", None)
        return payload


@dataclass(frozen=True)
class SearchResponse:
    query: str
    requested_mode: str
    used_mode: str
    locale: str
    results: list[SearchResult]
    timings_ms: dict[str, float]
    request_id: str
    fallback_triggered: bool = False
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "requested_mode": self.requested_mode,
            "used_mode": self.used_mode,
            "locale": self.locale,
            "results": [result.to_dict() for result in self.results],
            "timings_ms": self.timings_ms,
            "request_id": self.request_id,
            "fallback_triggered": self.fallback_triggered,
            "fallback_reason": self.fallback_reason,
        }
