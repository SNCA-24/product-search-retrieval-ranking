# Portfolio Walkthrough

This is the shortest useful way to explain the repo to a recruiter or interviewer.

## 30-second version

This project is a local-first product search and ranking system built on the Amazon ESCI dataset. It covers data prep, offline evaluation, lexical retrieval, vector retrieval, hybrid fusion, learning-to-rank, serving, latency benchmarking, and a thin UI for qualitative inspection. It was intentionally built and tuned on a 16 GB Mac Mini, so the final design reflects real local resource constraints rather than cloud assumptions.

## What to say first

- The system starts from joined ESCI parquet files plus query-source metadata.
- It builds a processed evaluation spine, a single-node OpenSearch index, and an XGBoost listwise ranker.
- Offline `ltr` is the best quality mode.
- Online `hybrid` is the default serving path.
- Online `ltr` was optimized until it became locally viable, then stopped at the best quality-latency tradeoff instead of being over-forced.

## The three decisions that matter most

1. `BM25` is the strongest unre-ranked baseline, so the project does not pretend lexical retrieval is weak.
2. `Hybrid` stays the default online path because it is safely within the local latency budget.
3. `LTR top 60` is the final online candidate depth because repeated sweeps showed it was the best local tradeoff.

## Demo flow

### 1. Open the UI

- Run the API:
  - `ESCI_PROFILE=full PYTHONPATH=src .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000`
- Open:
  - [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

### 2. Show the default path

- Query: `wireless mouse`
- Mode: `Hybrid`
- Point out:
  - latency strip
  - result cards
  - debug details
  - quality table
  - candidate-depth table

### 3. Show the richer path

- Switch mode to `Hybrid + LTR`
- Turn on debug details
- Point out:
  - cross-mode rank positions
  - feature snapshot
  - request-time ranking split

### 4. Show mode comparison

- Open the compare drawer
- Explain why the UI exists:
  - it makes retrieval and ranking differences visible
  - it is intentionally thin and not a separate product build

## Measured talking points

- Full-test offline quality:
  - BM25 `NDCG@10 0.3220`
  - Hybrid `0.2880`
  - Offline LTR `0.3753`
- Online latency:
  - Hybrid `P95 145.2 ms`
  - Optimized LTR single-run `P95 310.6 ms`
  - Repeated warm LTR top-60 median `P95 159.7 ms`

## Tradeoff story

- The project did not chase the highest-quality model blindly.
- It also did not stop at the first latency-safe baseline.
- Instead it kept both truths visible:
  - offline `ltr` is the quality ceiling
  - online `hybrid` is the safe default
  - optimized online `ltr` is now viable and explainable on local hardware
  - Phase `5` cross-encoder reranking is deferred future work rather than forced into the main ship

## Good example queries to mention

- `ashwaghanda extract`
  - shows semantic recovery from a misspelling
- `triggered donald trump jr`
  - shows lexical confusion corrected by hybrid plus LTR
- `belt for women guess`
  - shows a real LTR regression from brand over-weighting
- `silicone jar toys`
  - shows semantic category drift

## Files worth opening in an interview

- [README.md](../README.md)
- [docs/final_results.md](./final_results.md)
- [docs/failure_analysis.md](./failure_analysis.md)
- [docs/architecture.md](./architecture.md)
- [src/retrieval/service.py](../src/retrieval/service.py)
- [src/ranking/service.py](../src/ranking/service.py)
- [src/api/app.py](../src/api/app.py)

## Final framing

This repo is strongest when presented as:

- a relevance engineering project
- built under real hardware constraints
- with both offline rigor and a live inspection surface

It should not be framed as:

- a generic search demo
- a frontend project
- a cloud-scaled production system
