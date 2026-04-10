# Amazon ESCI Search Platform

Local-first product search, retrieval, and ranking system built on the Amazon ESCI dataset for a 16 GB Mac Mini. The repo now includes a thin inspection UI on top of the retrieval and ranking stack so the search behavior is visible, not just measurable.

The repo is frozen in its current shipped state:

- default online serving path: `hybrid`
- final online LTR configuration: `top 60`
- best quality analysis mode: offline `ltr`
- Phase `5` cross-encoder reranking: deferred future work, not part of the main ship

## Final status

- PRD phases `0-4` are implemented end to end on the local full profile.
- Phase `5` cross-encoder reranking is explicitly deferred future work and is not part of the shipped scope.
- Phase `6` serving is implemented with `FastAPI`, `OpenSearch`, `hybrid`, and `ltr` modes.
- A one-page UI at `/` was added beyond the original PRD to make the system legible for demos, screenshots, and qualitative analysis.
- Locked decisions:
  - Default online serving path: `hybrid`
  - Final online LTR configuration: `top 60`
  - Best quality analysis mode: offline `ltr`

## Measured full-profile results

### Quality

| System | NDCG@10 | MRR | Precision@10 | Recall@50 | Recall@100 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.3220 | 0.5665 | 0.2955 | 0.3778 | 0.4524 |
| Hybrid | 0.2880 | 0.4979 | 0.2706 | 0.3767 | 0.4591 |
| Offline LTR | 0.3753 | 0.6235 | 0.3439 | 0.4211 | 0.4818 |

### Online latency

| Mode | P50 ms | P95 ms | Notes |
| --- | ---: | ---: | --- |
| Hybrid | 120.0 | 145.2 | Latency-safe default online path |
| LTR after one optimization pass | 204.4 | 310.6 | Single-run result after removing major bottlenecks |
| LTR top-60 repeated warm runs | 118.0 median P50 | 159.7 median P95 | Stable local operating point |

### Candidate-depth sweep

| Online LTR depth | NDCG@10 | Median P95 ms | Mean P95 ms | Decision |
| --- | ---: | ---: | ---: | --- |
| 40 | 0.3629 | 189.9 | 204.0 | Lower quality and noisier latency |
| 50 | 0.3651 | 165.1 | 167.5 | Stable but slightly worse than `60` |
| 60 | 0.3666 | 159.7 | 162.6 | Final local quality-latency tradeoff |

## UI

The UI is deliberately thin: `FastAPI + Jinja2 + minimal JS + custom CSS`. It is framed as a search relevance demo and qualitative inspection console, not as a separate frontend product.

What it shows:

- search box, mode selector, top-k, brand/color filters, debug toggle
- result cards with title, brand, color, locale, product id, scores, badges, and preview text
- summary strip with mode, result count, end-to-end latency, retrieval time, ranking time, rerank time, and request id
- expandable ranking details and feature snapshots
- compare drawer for `bm25` vs `hybrid` vs `ltr`
- session query history

### Screenshots

Hybrid search console:

![Hybrid search console](assets/screenshots/search-console-hybrid-window.png)

LTR debug view:

![LTR debug view](assets/screenshots/search-console-ltr-debug-window.png)

Compare drawer:

![Compare drawer](assets/screenshots/search-console-compare-window.png)

## Architecture and tradeoffs

The architecture is a local-first multi-stage retrieval and ranking pipeline:

1. Joined ESCI parquet files plus `sources.csv`
2. Phase 1 prep into processed train/test tables, qrels, and search documents
3. Product embedding checkpoint generation
4. Single-node OpenSearch index for BM25 and vector retrieval
5. Hybrid RRF fusion and feature generation
6. XGBoost listwise ranker
7. FastAPI service and inspection UI

Key tradeoffs:

- `BM25` is the strongest unre-ranked full-test baseline in the saved offline reports.
- `Hybrid` remains the default online demo path because it already meets latency comfortably, keeps the serving stack aligned with the retrieval-plus-ranking architecture, and is the clean fallback path for richer online experiments.
- Offline `ltr` is the best quality analysis mode.
- Naive online `ltr` was too slow, so one targeted optimization pass was applied:
  - reuse one query embedding per request
  - remove duplicate retrieval work inside the LTR path
  - precompute product-side online stats
  - constrain the online candidate depth
- Repeated warm-state sweeps established `top 60` as the final online LTR configuration on this machine.
- The UI compare drawer exposed a real concurrent lazy-init issue in the embedding model path, so the retriever now guards model and ranker initialization with locks.

### Deferred future work

Phase `5` cross-encoder reranking is intentionally not in the main shipped path. It is best treated as a future extension branch because:

- it adds another expensive CPU inference stage on a 16 GB Mac Mini
- it would increase serving and fallback complexity materially
- the current repo already has a clear and defensible final state without it

If revisited later, it should start as an offline-only experiment before any online integration work.

See [docs/architecture.md](docs/architecture.md) and [docs/final_results.md](docs/final_results.md) for the fuller writeup.
See [docs/portfolio_walkthrough.md](docs/portfolio_walkthrough.md) for the short recruiter/interviewer demo script.

## Quickstart

Use a clean project-local Python `3.11` or `3.12` interpreter, not the Anaconda base interpreter.

### Base setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
python scripts/doctor.py --profile dev
python scripts/prepare_data.py --profile dev
python scripts/run_eval.py --profile dev --system baseline --split test --gain-mapping default
```

### Retrieval, ranking, and UI

```bash
pip install -e ".[retrieval,ranking,dev]"
docker-compose up -d opensearch
python scripts/build_index.py --profile full create-index
python scripts/build_index.py --profile full index-documents
python scripts/train_ranker.py --profile full --objective listwise --gain-mapping default
ESCI_PROFILE=full PYTHONPATH=src .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Then open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

## Repo layout

- `configs/`: service, model, and latency defaults
- `scripts/`: operational entrypoints
- `src/`: data prep, evaluation, indexing, retrieval, ranking, API, and UI code
- `data/`: processed artifacts, caches, models, evaluation reports, and OpenSearch data
- `docs/`: architecture, results, failure analysis, setup, lessons learned, and the interview walkthrough
- `assets/screenshots/`: captured UI images used in the README

## Evidence

- [docs/final_results.md](docs/final_results.md)
- [docs/failure_analysis.md](docs/failure_analysis.md)
- [docs/portfolio_walkthrough.md](docs/portfolio_walkthrough.md)
- [data/evaluation/full/reports/bm25_test_default.json](data/evaluation/full/reports/bm25_test_default.json)
- [data/evaluation/full/reports/hybrid_test_default.json](data/evaluation/full/reports/hybrid_test_default.json)
- [data/evaluation/full/reports/ltr_test_default.json](data/evaluation/full/reports/ltr_test_default.json)
- [data/evaluation/full/reports/latency_search_hybrid.json](data/evaluation/full/reports/latency_search_hybrid.json)
- [data/evaluation/full/reports/latency_search_ltr.json](data/evaluation/full/reports/latency_search_ltr.json)
- [data/evaluation/full/reports/ltr_candidate_depth_repeats_40_50_60.json](data/evaluation/full/reports/ltr_candidate_depth_repeats_40_50_60.json)
