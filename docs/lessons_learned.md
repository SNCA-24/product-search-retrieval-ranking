# Lessons Learned

## Final narrative

- `BM25` remained the strongest unre-ranked full-test baseline, so the project never treated lexical retrieval as a strawman.
- `Hybrid` stayed the default online path because it met the latency target comfortably and kept the live system simple.
- Offline `ltr` produced the best quality metrics and therefore became the main analysis mode for ranking quality.
- Naive online `ltr` was initially too slow, but one targeted optimization pass removed the largest avoidable bottlenecks.
- Repeated candidate-depth sweeps showed `top 60` is the best local quality-latency tradeoff for online `ltr`.
- Adding the thin UI was worth it because it made ranking behavior inspectable without turning the repo into a separate frontend project.
- The compare drawer surfaced a real concurrent lazy-init bug in the retriever singleton, which is exactly the kind of issue a purely offline pipeline would miss.

## What this project demonstrates well

- disciplined scope control under local hardware limits
- clear separation between offline quality and online serving constraints
- willingness to stop tuning once the tradeoff became defensible
- practical retrieval, ranking, and latency engineering rather than benchmark chasing

## What was intentionally not forced into the main ship

- Phase `5` cross-encoder reranking

Why:

- it would add another CPU-heavy inference stage on the same 16 GB local machine
- it would increase serving, timeout, and fallback complexity materially
- the repo already has a clean and defensible shipped state without it

## If the project continued

The next highest-value extensions would be:

- offline-only cross-encoder reranker experiments before any online integration
- stronger product-type features for fashion and accessory queries
- better ambiguity handling for mixed-intent semantic queries
- cloud or multi-node experiments only after the local tradeoffs stop being the main bottleneck
