from __future__ import annotations

from types import SimpleNamespace

from common.types import SearchRequest, SearchResult
from ranking.service import OnlineLTRRanker


def _make_result(
    *,
    product_id: str,
    title: str,
    brand: str = "",
    color: str = "",
    score: float,
    rank: int,
    product_text: str,
) -> SearchResult:
    return SearchResult(
        product_id=product_id,
        product_locale="us",
        product_title=title,
        product_brand=brand,
        product_color=color,
        score=score,
        rank=rank,
        searchable_text=product_text,
        raw_scores={},
        product_description="desc words",
        product_bullet_point="bullet words",
        product_text=product_text,
    )


def test_search_result_to_dict_hides_internal_text_fields() -> None:
    result = _make_result(
        product_id="p1",
        title="Blue mug",
        brand="Acme",
        color="Blue",
        score=1.0,
        rank=1,
        product_text="Blue mug ceramic",
    )

    payload = result.to_dict()

    assert "product_description" not in payload
    assert "product_bullet_point" not in payload
    assert "product_text" not in payload


def test_build_feature_frame_uses_bm25_vector_union_and_defaults() -> None:
    ranker = OnlineLTRRanker(
        settings=SimpleNamespace(
            resolved_profile=lambda profile: profile,
            profile_config=lambda profile: SimpleNamespace(top_k=100),
        ),
        profile="dev",
    )
    request = SearchRequest(query="acme blue mug", mode="ltr", locale="us", k=10)

    bm25_results = [
        _make_result(
            product_id="p1",
            title="Acme blue mug",
            brand="Acme",
            color="Blue",
            score=12.0,
            rank=1,
            product_text="acme blue mug ceramic",
        )
    ]
    vector_results = [
        _make_result(
            product_id="p2",
            title="Ceramic cup",
            brand="Acme",
            color="White",
            score=0.82,
            rank=1,
            product_text="blue coffee mug cup",
        )
    ]
    hybrid_results = [
        _make_result(
            product_id="p1",
            title="Acme blue mug",
            brand="Acme",
            color="Blue",
            score=0.03,
            rank=1,
            product_text="acme blue mug ceramic",
        )
    ]

    features = ranker._build_feature_frame(
        request,
        bm25_results=bm25_results,
        vector_results=vector_results,
        hybrid_results=hybrid_results,
    ).sort_values("product_id")

    assert features["product_id"].tolist() == ["p1", "p2"]
    p1 = features[features["product_id"] == "p1"].iloc[0]
    p2 = features[features["product_id"] == "p2"].iloc[0]

    assert p1["bm25_score"] == 12.0
    assert p1["hybrid_rank"] == 1
    assert p1["title_exact_match"] == 1
    assert p1["brand_exact_match"] == 1

    assert p2["bm25_score"] == 0.0
    assert p2["hybrid_rank"] == 101
    assert p2["vector_score"] == 0.82
    assert p2["source_prior"] == 0.0
