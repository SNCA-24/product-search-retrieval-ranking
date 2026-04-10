# Final Results

This document records the locked local-hardware decisions and the measured outputs used in the README.

## Locked decisions

- Default online serving path: `hybrid`
- Final online LTR configuration: `top 60`
- Best quality analysis mode: offline `ltr`
- Phase `5` cross-encoder reranking: deferred future work

## Framing

- Baseline `hybrid` already met the local latency target.
- Naive online `ltr` was too slow on the 16 GB Mac Mini.
- One targeted optimization pass removed the largest avoidable bottlenecks in the online `ltr` path.
- Repeated 40/50/60 sweeps showed `top 60` is the best local quality-latency tradeoff.
- Final online `ltr` is viable on local hardware, but `hybrid` remains the default serving path because it is simpler and already safely within budget.
- The project is frozen in this state rather than extending the main ship with a Phase `5` cross-encoder reranker.

## Full-profile quality

| System | NDCG@10 | MRR | Precision@10 | Recall@50 | Recall@100 | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| BM25 | 0.3220 | 0.5665 | 0.2955 | 0.3778 | 0.4524 | Strongest unre-ranked full-test baseline |
| Hybrid | 0.2880 | 0.4979 | 0.2706 | 0.3767 | 0.4591 | Default online serving path |
| Offline LTR | 0.3753 | 0.6235 | 0.3439 | 0.4211 | 0.4818 | Best quality analysis mode |

## Online latency

| Mode | P50 ms | P95 ms | Notes |
| --- | ---: | ---: | --- |
| Hybrid | 120.0 | 145.2 | Latency-safe local baseline |
| LTR before optimization | 717.4 | 893.0 | Too slow for the target budget |
| LTR after one optimization pass | 204.4 | 310.6 | Materially improved, but one run alone was too close to target |

## Repeated candidate-depth sweep

Repeated warm-state `25`-query latency runs on the full profile:

| Depth | NDCG@10 | Median P95 ms | Mean P95 ms | Notes |
| --- | ---: | ---: | ---: | --- |
| 40 | 0.3629 | 189.9 | 204.0 | Lower quality and noisier latency |
| 50 | 0.3651 | 165.1 | 167.5 | Stable but slightly worse than `60` |
| 60 | 0.3666 | 159.7 | 162.6 | Final online LTR setting |

## UI deliverables

The repo now includes a thin search inspection UI that was added beyond the original PRD:

- [Hybrid screenshot](../assets/screenshots/search-console-hybrid-window.png)
- [LTR debug screenshot](../assets/screenshots/search-console-ltr-debug-window.png)
- [Compare drawer screenshot](../assets/screenshots/search-console-compare-window.png)

## Notes

- `BM25` remains the strongest saved unre-ranked full-test baseline.
- `Hybrid` remains the default live path because it keeps the live serving stack aligned with the retrieval-plus-ranking system and already satisfies the latency budget.
- The compare drawer triggered a concurrent first-load path, which exposed a lazy-init race in the retriever singleton. That is now fixed with initialization locks.

## Evidence

- `data/evaluation/full/reports/bm25_test_default.json`
- `data/evaluation/full/reports/hybrid_test_default.json`
- `data/evaluation/full/reports/ltr_test_default.json`
- `data/evaluation/full/reports/latency_search_hybrid.json`
- `data/evaluation/full/reports/latency_search_ltr.json`
- `data/evaluation/full/reports/ltr_candidate_depth_repeats_40_50_60.json`
