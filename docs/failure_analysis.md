# Failure Analysis

This document turns the saved full-profile artifacts into a concrete error analysis instead of a placeholder taxonomy.

## Locked operating decisions

- Default online serving path: `hybrid`
- Final online LTR setting for local hardware: `top 60`
- Best quality analysis mode: offline `ltr`
- Cold-start and warm-state latency must be treated separately for online `ltr`

## What the aggregate results say

- `BM25` is the strongest unre-ranked full-test baseline.
- `Hybrid` is not the best offline metric winner, but it is still the best default interactive path because it stays well within the latency target.
- Offline `ltr` improves quality meaningfully over both unre-ranked paths, but it is not uniformly better on every query.
- The main error modes are not random; they cluster around misspellings, semantic drift, brand-heavy queries, and product-type ambiguity.

## Representative wins

### 1. Misspelling plus product intent recovery

- Query: `ashwaghanda extract`
- Query id: `10648`
- Full-test delta:
  - BM25 `NDCG@10 = 0.0000`
  - Hybrid `0.5869`
  - LTR `0.9052`

What happened:

- BM25 failed almost completely because the query misspells `ashwagandha`.
- Hybrid recovered the product family by semantic retrieval.
- LTR then promoted the most obviously on-intent supplement items to the top.

Why this matters:

- This is the best case for the full stack: vector retrieval recovers recall, then LTR sharpens product-type precision.

### 2. Semantic recovery from a near-title miss

- Query: `triggered donald trump jr`
- Query id: `105261`
- Full-test delta:
  - BM25 `NDCG@10 = 0.0000`
  - Hybrid `0.5000`
  - LTR `1.0000`

What happened:

- BM25 ranked `Figgered: Donald Trump Jr.` first because it over-relied on lexical similarity.
- Hybrid surfaced the real target, `Triggered: How the Left Thrives on Hate and Wants to Silence Us`.
- LTR moved that exact item to rank 1 and preserved it there.

Why this matters:

- This is a clean demonstration of why the repo needs more than lexical retrieval alone.

### 3. Retrieval fusion rescue

- Query: `swiss gear carry on luggage`
- Query id: `99888`
- Full-test delta:
  - BM25 `NDCG@10 = 0.0650`
  - Hybrid `0.7379`
  - LTR `0.3646`

What happened:

- BM25 was distracted by lexical overlap on `Swiss Gear` accessories like luggage tags.
- Hybrid surfaced the actual `SwissGear` carry-on luggage products correctly.
- LTR regressed from the hybrid ranking on this query, which is why hybrid remains a first-class serving mode and not just a stepping stone.

Why this matters:

- This query is a reminder that hybrid retrieval is not just infrastructure for LTR. Sometimes it is already the right answer.

## Representative regressions

### 1. Brand prior overpowering product-type intent

- Query: `belt for women guess`
- Query id: `14862`
- Full-test delta:
  - BM25 `NDCG@10 = 0.6680`
  - Hybrid `0.6238`
  - LTR `0.0976`

Observed pattern:

- BM25 and hybrid still surfaced several relevant `GUESS` belt-related results and belt-dress products.
- LTR over-weighted `GUESS` brand affinity and accepted unrelated `GUESS` apparel and bag products into the top ranks.

Likely cause:

- The feature set has strong brand-match and retrieval-score signals, but it does not model product-type compatibility strongly enough for brand-constrained fashion queries.

### 2. Category drift under partial lexical overlap

- Query: `silicone jar toys`
- Query id: `93275`
- Full-test delta:
  - BM25 `NDCG@10 = 0.6399`
  - Hybrid `0.0829`
  - LTR `0.1065`

Observed pattern:

- BM25 found a relevant `NoGoo Silicone Jar` result early.
- Hybrid drifted toward silicone-based toy/fidget results and jar accessories.
- LTR did not fully recover from the candidate pool drift.

Likely cause:

- Once the candidate set mixes two semantic clusters, `jar` tools and `silicone toys`, the current feature set does not have a strong enough concept-level disambiguation signal.

### 3. Long-form product-type ambiguity

- Query: `cute storage shelves for floor`
- Query id: `31082`
- Full-test delta:
  - BM25 `NDCG@10 = 0.5700`
  - Hybrid `0.0000`
  - LTR `0.0663`

Observed pattern:

- The lexical baseline benefited from direct overlap with shelving vocabulary.
- Hybrid and LTR both struggled because the semantic space appears to over-generalize from `cute`, `storage`, and `floor`.

Likely cause:

- This looks like a retrieval-recall issue more than a ranking-only issue. If the right shelf candidates are not in the pool, LTR cannot repair it.

## Failure taxonomy grounded in the saved runs

### Query classes where the stack helps most

- Misspellings and phonetic variants
  - `ashwaghanda extract`
- Title-near queries with one bad token
  - `triggered donald trump jr`
- Brand plus product-family queries where semantic retrieval recovers the right catalog neighborhood
  - `swiss gear carry on luggage`

### Query classes where the stack still struggles

- Brand-heavy fashion queries with weak product-type constraints
  - `belt for women guess`
- Queries that mix two plausible semantic categories
  - `silicone jar toys`
- Long-tail natural language queries where candidate recall collapses early
  - `cute storage shelves for floor`

## Operational lesson from the UI

- The compare drawer sends parallel requests for `bm25`, `hybrid`, and `ltr`.
- That exposed a concurrent lazy-init race in the shared retriever singleton during first model load.
- The fix was to guard embedding-model and ranker initialization with locks so the live UI no longer falls back under parallel first-use traffic.

## Practical takeaways

- Keep `hybrid` as the default online mode because it is fast, stable, and often already good enough.
- Use offline `ltr` as the quality ceiling for analysis and model comparison.
- Treat online `ltr` as a selective upgrade path whose value depends on the query class.
- If the project continues, the next quality gains should likely come from:
  - stronger product-type features
  - better fashion/accessory intent handling
  - stricter candidate-pool filtering for ambiguous semantic queries
