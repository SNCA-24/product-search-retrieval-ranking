from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.schemas import ExplainResponseModel, HealthResponseModel, SearchResponseModel
from common.config import AppSettings, load_settings
from common.io import read_json
from common.types import SearchRequest
from indexing.opensearch import current_index_count
from retrieval.service import OpenSearchRetriever

app = FastAPI(title="Amazon ESCI Search Platform", version="0.1.0")
API_ROOT = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=API_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=str(API_ROOT / "templates"))


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return load_settings()


@lru_cache(maxsize=1)
def get_retriever() -> OpenSearchRetriever:
    settings = get_settings()
    return OpenSearchRetriever(settings=settings, profile=settings.default_profile)


def _opensearch_connected(settings: AppSettings) -> bool:
    try:
        current_index_count(settings)
        return True
    except Exception:
        return False


def _quality_rows(settings: AppSettings) -> list[dict[str, str]]:
    profile = settings.default_profile
    lookup = [
        ("BM25", settings.evaluation_dir(profile) / "reports" / "bm25_test_default.json"),
        ("Hybrid", settings.evaluation_dir(profile) / "reports" / "hybrid_test_default.json"),
        ("Offline LTR", settings.evaluation_dir(profile) / "reports" / "ltr_test_default.json"),
    ]
    rows: list[dict[str, str]] = []
    for label, path in lookup:
        if not path.exists():
            continue
        report = read_json(path)
        summary = report["summary"]
        rows.append(
            {
                "label": label,
                "ndcg_at_10": f"{summary['ndcg_at_10']:.4f}",
                "mrr": f"{summary['mrr']:.4f}",
            }
        )
    return rows


def _candidate_depth_summary(settings: AppSettings) -> list[dict[str, str]]:
    path = settings.evaluation_dir(settings.default_profile) / "reports" / "ltr_candidate_depth_repeats_40_50_60.json"
    if not path.exists():
        return []
    rows = read_json(path)["results"]
    summary: dict[int, list[float]] = {}
    quality: dict[int, float] = {}
    for row in rows:
        summary.setdefault(int(row["depth"]), []).append(float(row["p95_ms"]))
        quality[int(row["depth"])] = float(row["ndcg_at_10"])
    output: list[dict[str, str]] = []
    for depth in sorted(summary):
        values = sorted(summary[depth])
        median = values[len(values) // 2]
        output.append(
            {
                "depth": str(depth),
                "ndcg_at_10": f"{quality[depth]:.4f}",
                "median_p95_ms": f"{median:.1f}",
            }
        )
    return output


@app.get("/", response_class=HTMLResponse)
def search_console(
    request: Request,
    q: str = Query(default=""),
    mode: str = Query(default="hybrid"),
    brand: str = Query(default=""),
    color: str = Query(default=""),
    k: int = Query(default=10),
    debug: int = Query(default=0),
    compare: int = Query(default=0),
) -> HTMLResponse:
    settings = get_settings()
    mode_options = [
        {"value": "bm25", "label": "BM25"},
        {"value": "vector", "label": "Vector"},
        {"value": "hybrid", "label": "Hybrid"},
        {"value": "ltr", "label": "Hybrid + LTR"},
    ]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_title": "ESCI Search Console",
            "subtitle": "Search relevance demo for BM25, vector, hybrid, and LTR",
            "mode_options": mode_options,
            "top_k_options": [10, 20, 50],
            "default_mode": "hybrid",
            "latency_target_ms": settings.latency_budgets_ms["end_to_end_p95_target"],
            "quality_rows": _quality_rows(settings),
            "candidate_depth_rows": _candidate_depth_summary(settings),
            "locked_decisions": {
                "default_online": "Hybrid",
                "final_online_ltr": "Top 60",
                "best_quality": "Offline LTR",
            },
            "opensearch_connected": _opensearch_connected(settings),
            "initial_state": {
                "query": q,
                "mode": mode,
                "brand": brand,
                "color": color,
                "k": k,
                "debug": bool(debug),
                "compare": bool(compare),
            },
        },
    )


@app.get("/health", response_model=HealthResponseModel)
def health() -> HealthResponseModel:
    settings = get_settings()
    services = {
        name: {
            "host": endpoint.host,
            "port": endpoint.port,
            "url": endpoint.url,
            "connected": _opensearch_connected(settings) if name == "opensearch" else True,
        }
        for name, endpoint in settings.services.items()
    }
    return HealthResponseModel(status="ok", profile=settings.default_profile, services=services)


@app.get("/debug/search", response_model=SearchResponseModel)
def debug_search(
    q: str = Query(..., min_length=1),
    mode: str = Query("bm25"),
    brand: str | None = Query(default=None),
    color: str | None = Query(default=None),
    locale: str = Query("us"),
    k: int = Query(10, ge=1, le=100),
) -> SearchResponseModel:
    response = get_retriever().search(
        SearchRequest(query=q, mode=mode, brand=brand, color=color, locale=locale, k=k)
    )
    return SearchResponseModel(**response.to_dict())


@app.get("/search", response_model=SearchResponseModel)
def search(
    q: str = Query(..., min_length=1),
    brand: str | None = Query(default=None),
    color: str | None = Query(default=None),
    locale: str = Query("us"),
    k: int = Query(10, ge=1, le=100),
    mode: str = Query("hybrid"),
) -> SearchResponseModel:
    response = get_retriever().search(
        SearchRequest(query=q, mode=mode, brand=brand, color=color, locale=locale, k=k),
        allow_fallbacks=True,
    )
    return SearchResponseModel(**response.to_dict())


@app.get("/explain", response_model=ExplainResponseModel)
def explain(
    q: str = Query(..., min_length=1),
    product_id: str = Query(..., min_length=1),
    mode: str = Query("bm25"),
    brand: str | None = Query(default=None),
    color: str | None = Query(default=None),
    locale: str = Query("us"),
) -> ExplainResponseModel:
    try:
        payload = get_retriever().explain(
            SearchRequest(query=q, mode=mode, brand=brand, color=color, locale=locale),
            product_id=product_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ExplainResponseModel(payload=payload)
