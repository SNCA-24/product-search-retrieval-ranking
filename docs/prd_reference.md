Amazon hosts the dataset on its official Amazon Science page, which links to the public GitHub repo. The official repo includes the dataset files and documents the core fields, two dataset versions, and task definitions. There is also a Hugging Face mirror of the joined dataset, with reported size around **2.52 GB** and about **2.68M rows**, which is useful as a fallback access path. ([Amazon Science](https://www.amazon.science/code-and-datasets/shopping-queries-dataset-a-large-scale-esci-benchmark-for-improving-product-search))

For practicality on your Mac mini, I recommend we **scope the project to the English/US slice of the reduced Task-1 ranking dataset first**. In the official repo, the reduced version has **48,300 unique queries** and **1,118,011 judgments** overall, and the English/US portion has **29,844 queries** and **601,354 judgments**. The available fields include query text, product text, brand, color, locale, split flags, and ESCI labels, which is exactly what we need for lexical retrieval, filters, feature engineering, LTR, and a realistic product-search API. ([GitHub](https://github.com/amazon-science/esci-data))

# **PRD — Enterprise Product Search / Retrieval / Ranking Platform**

## **1\. Project title**

**Amazon ESCI Search Ranking Platform**

## **2\. Executive summary**

Build a **local-first, zero-budget, enterprise-style product search platform** using the Amazon Shopping Queries Dataset (ESCI). The system will support:

* lexical retrieval with **BM25 as the baseline**  
* **vector retrieval using precomputed sentence-transformer embeddings**  
* **hybrid retrieval in Phase 2** using BM25 \+ vector search with **RRF fusion**  
* offline relevance evaluation  
* learning-to-rank experimentation  
* strict latency budgeting  
* a debug API first, then a production-style search API  
* optional reranking only if it is justified by quality-vs-latency tradeoffs

The backbone is aligned with OpenSearch’s supported capabilities: **BM25 retrieval, vector/k-NN retrieval, hybrid fusion with RRF, rank evaluation, Learning to Rank with XGBoost/RankLib, and reranking via search pipelines**. This project keeps **retrieval inference** in scope while keeping **neural retriever training** out of scope for the current zero-budget build. ([OpenSearch Documentation](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/?utm_source=chatgpt.com))

## **3\. Why this project exists**

The portfolio goal is to demonstrate that you can build a **real retrieval and ranking system**, not just train a model in isolation.

This project should prove you can handle:

* search system design  
* relevance engineering  
* ranking experimentation  
* offline evaluation  
* API design  
* latency tradeoffs  
* production constraints and fallbacks

## **4\. Product vision**

Given a user query like “wireless mouse logitech” or “pink running shoes”, the system should:

* retrieve plausible product candidates  
* rank them using progressively stronger methods  
* expose transparent evaluation metrics  
* stay within a target latency budget  
* support debugging and failure analysis  
* degrade gracefully when a later-stage model is too slow

## **5\. Final dataset decision**

### **Chosen dataset**

**Amazon Shopping Queries Dataset (ESCI)**

### **Official availability**

* Official Amazon Science release page with public access link ([Amazon Science](https://www.amazon.science/code-and-datasets/shopping-queries-dataset-a-large-scale-esci-benchmark-for-improving-product-search))  
* Official GitHub repository with dataset structure and files ([GitHub](https://github.com/amazon-science/esci-data))  
* Hugging Face mirror as secondary access route ([Hugging Face](https://huggingface.co/datasets/tasksource/esci))

### **Dataset fields we will use**

From the official repo, the examples/products files expose fields such as:

* `query`  
* `query_id`  
* `product_id`  
* `product_locale`  
* `esci_label`  
* `split`  
* `product_title`  
* `product_description`  
* `product_bullet_point`  
* `product_brand`  
* `product_color`  
* `source` ([GitHub](https://github.com/amazon-science/esci-data))

### **Scope decision for this project**

Use:

* **English/US only**  
* **reduced Task-1 ranking version first**  
* official train/test split  
* local dev slice for faster iteration if needed

### **Why this dataset wins**

It gives you one unified pipeline for:

* retrieval  
* feature engineering  
* LTR  
* filtering  
* relevance labels  
* search-product demo realism

It is much better aligned to the current project scope than splitting time across three unrelated datasets.

## **6\. Users and use cases**

### **Primary user**

A shopper or search user looking for the best products for a query.

### **Secondary user**

An engineer or PM evaluating relevance quality and system latency.

### **Core use cases**

* search by natural query  
* inspect top results  
* filter by brand/color/locale  
* compare ranking methods  
* understand why ranking improved or regressed  
* evaluate whether reranking is worth the latency

## **7\. Goals**

### **Primary goals**

* build an end-to-end product search ranking system  
* create a robust offline evaluation framework  
* implement LTR experimentation with strong ML signal  
* expose a minimal API early and a production-style API later  
* enforce latency-aware design  
* produce clear portfolio-ready evidence of tradeoff thinking

### **Secondary goals**

* support explain/debug workflows  
* support **hybrid lexical \+ vector retrieval in the core system**  
* support future **semantic retrieval model training** as an extension  
* support future NLP-heavy retrieval improvements only after the ranking stack is stable

## **8\. Non-goals for current scope**

Not in current scope:

* **training a semantic retriever / two-tower model from scratch**  
* large neural retriever training  
* multi-node OpenSearch  
* Kubernetes deployment  
* real-time streaming ingestion  
* large rerankers or GPU-heavy inference  
* multilingual support beyond the chosen US/English slice


## **9\. Success metrics**

### **Relevance metrics**

Use:

* **NDCG@10**  
* **MRR**  
* **Precision@10**  
* **Recall@50 / Recall@100** for candidate quality

OpenSearch provides a rank-eval endpoint specifically for evaluating ranked search quality. ([OpenSearch Documentation](https://docs.opensearch.org/3.0/api-reference/search-apis/rank-eval/?utm_source=chatgpt.com))

### **System metrics**

* P50 latency  
* P95 latency  
* timeout rate  
* zero-result rate  
* fallback-trigger rate

### **Target latency**

Initial design target:

* **end-to-end P95 \= 250 ms**

Initial stage budgets:

* API/network overhead: **30 ms**  
* retrieval: **50 ms**  
* feature hydration \+ L2 ranking: **70 ms**  
* reranking: **100 ms provisional**

The reranking budget is a **hypothesis**, not a promise. It must be benchmarked before adoption.

## **10\. System architecture**

## **Core components**

### **A. Data preparation layer**

Responsibilities:

* read official parquet/csv files  
* filter to US/English slice  
* join examples and product metadata  
* clean missing text fields  
* create train/test tables  
* generate search documents

### **B. OpenSearch indexing layer**

Responsibilities:

* create the product search index  
* configure **text, keyword/filterable, and vector fields**  
* index product documents for **BM25 retrieval**  
* generate and store **dense embeddings** for product text using a lightweight sentence-transformer model  
* configure **k-NN / vector search mappings**  
* support **hybrid retrieval** by combining BM25 and vector search  
* support **RRF-based fusion** as the default hybrid strategy  
* retain clean separability between:  
  * BM25 baseline  
  * vector-only retrieval  
  * hybrid retrieval

### **C. Offline evaluation layer**

Responsibilities:

* build qrels from ESCI labels  
* compute relevance metrics  
* compare experiments side by side  
* log outputs to MLflow and experiment reports

### **D. Ranking layer**

Responsibilities:

* generate ranking features  
* train multiple XGBoost rankers  
* evaluate pointwise vs pairwise vs listwise setups  
* export best model for serving

### **E. Serving layer**

Responsibilities:

* expose minimal `/debug/search` early  
* later expose `/search`, `/health`, `/explain`  
* apply latency budget logic  
* trigger graceful degradation

### **F. Experiment tracking layer**

Responsibilities:

* track params, metrics, artifacts, and chosen models  
* support reproducibility and side-by-side experiment review

## **11\. Tech stack**

### **Core stack**

* Python  
* FastAPI  
* OpenSearch  
* Pandas or Polars  
* XGBoost  
* MLflow  
* **sentence-transformers**  
* Docker Compose  
* pytest  
* GitHub Actions

### **Why this stack**

* OpenSearch supports **vector search, hybrid search pipelines, RRF-based score ranking, LTR, rank evaluation, and reranking**. ([OpenSearch Documentation](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/?utm_source=chatgpt.com))  
* XGBoost supports ranking objectives including `rank:pairwise` and `rank:ndcg`, with `rank:ndcg` documented as LambdaMART-style ranking. ([XGBoost Documentation](https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html?utm_source=chatgpt.com))  
* MLflow provides experiment tracking for params, metrics, and artifacts during model development.  
* sentence-transformers provides a practical local path for embedding inference without turning the project into a neural-training-heavy effort. 

## **12\. Detailed phase plan**

## **Phase 1 — Dataset prep and evaluation spine**

### **Objective**

Create the one source of truth for experiments.

### **Build**

* loader for official ESCI files  
* US-only reduced-version filter  
* merged training table  
* label mapping from ESCI labels to ranking relevance grades, with `E=3, S=2, C=1, I=0` as the default project mapping  
* document alternative gain mappings for later experimentation, including the Amazon baseline script’s compressed mapping  
* verify that the parquet assets are fully materialized locally before running full preprocessing, since the repo may initially contain Git LFS pointer files instead of payload data   
* evaluation query groups  
* metric runner

### **Outputs**

* cleaned parquet tables  
* `queries.csv`  
* `judgments.csv`  
* `run_eval.py`  
* baseline data-quality report

### **Acceptance criteria**

* one repeatable preprocessing command  
* train/test split is reproducible  
* offline metrics run successfully on a baseline result set

---

## **Phase 2 —  BM25 baseline, vector retrieval, hybrid fusion, and minimal debug API**

### **Objective**

Stand up the first full retrieval layer with:

* **BM25 as the baseline**  
* **vector retrieval as the semantic candidate source**  
* **hybrid BM25 \+ vector retrieval** using RRF  
* a minimal debug API for result inspection

### **Build**

* OpenSearch index mapping for:  
  * text fields  
  * filterable keyword fields  
  * vector field(s)  
* product indexing pipeline  
* BM25 search baseline  
* embedding generation pipeline using a lightweight sentence-transformer model  
* query embedding generation at search time for vector/hybrid retrieval  
* save embeddings in checkpointed local files (`.parquet` / `.npy`) before OpenSearch indexing  
* vector indexing pipeline  
* vector-only top-K retrieval  
* hybrid retrieval using **BM25 \+ vector search \+ RRF fusion**  
* **offline caching for benchmark/eval runs**  
* **minimal `GET /debug/search`**

### **Retrieval modes to support**

* BM25 only  
* vector only  
* hybrid BM25 \+ vector

### **API behavior**

The endpoint should:

* accept query text  
* accept small optional filters  
* allow a `mode` parameter such as:  
  * `bm25`  
  * `vector`  
  * `hybrid`  
* directly query OpenSearch  
* return top results with core debug fields, including which retrieval mode was used

No caching, no fallbacks, no auth yet.

### **Outputs**

* index creation script  
* indexing script  
* embedding generation script  
* hybrid retrieval script/query builder  
* checkpointed embedding artifacts  
* debug API  
* retrieval comparison report:  
  * BM25 vs vector vs hybrid

### **Acceptance criteria**

* BM25 baseline runs locally  
* vector retrieval runs locally  
* hybrid retrieval runs locally  
* embedding generation and indexing are restartable independently  
* offline metrics run for all three retrieval modes  
* engineer can manually inspect good and bad queries quickly  
* BM25 remains the official baseline for later ranking experiments

OpenSearch’s score-ranker processor uses **RRF** to combine multiple query result sets, which is exactly the right fit for this phase.

---

## **Phase 3 — Feature engineering and LTR data pipeline**

### **Objective**

Prepare strong ranking inputs.

### **Candidate feature groups**

* BM25 score  
* term overlap  
* title exact match  
* title token coverage  
* brand exact match  
* color mention match  
* description length  
* bullet-point length  
* popularity/source priors if available  
* query length bucket  
* product text completeness  
* text-field coverage score  
* vector similarity score  
* BM25 rank position  
* vector rank position  
* hybrid/RRF rank position  
* normalized retrieval scores if available

### **Outputs**

* feature extraction module  
* grouped ranking dataset  
* training/validation split strategy  
* feature dictionary

### **Acceptance criteria**

* all features are generated reproducibly  
* no leakage across split boundaries  
* features can be reused across all ranking experiments

---

## **Phase 4 — MLflow-backed core ML experimentation**

### **Objective**

Show real MLE depth through meaningful ranking comparisons while keeping every run tracked and reproducible from the start.

### **Build**

* local MLflow tracking setup  
* experiment naming convention  
* automatic logging wrapper for:  
  * model objective  
  * params  
  * metrics  
  * artifacts  
  * feature schema version  
  * data version  
* grouped ranking training pipeline  
* evaluation pipeline for side-by-side ranking experiments  
* gain-mapping configuration support so ranking runs can be repeated under different relevance-gain schemes without changing core training code

### **Experiments**

#### **Model A**

**Pointwise XGBoost**

* baseline regression/classification-style scorer

#### **Model B**

**Pairwise XGBoost**

* `rank:pairwise`

#### **Model C**

**Listwise XGBoost**

* `rank:ndcg`

### **Required analysis**

* A vs B vs C on the same feature set  
* metric comparison  
* training-time comparison  
* scoring-latency comparison  
* feature importance analysis  
* failure buckets by query type  
* sensitivity analysis for relevance gain mapping:  
  * primary mapping: E=3, S=2, C=1, I=0  
  * alternative compressed mapping inspired by the Amazon baseline script: E=1.0, S=0.1, C=0.01, I=0.0  
* compare how gain mapping changes:  
  * NDCG / MRR  
  * model feature importance  
  * ranking behavior for borderline **Substitute vs Complement** cases  
  * qualitative top-K ordering on representative queries

### **Outputs**

* local MLflow UI  
* training scripts  
* experiment table  
* final chosen L2 model  
* model comparison report  
* reproducibility checklist

### **Acceptance criteria**

* every experiment is logged in MLflow  
* at least one ranking model improves over the **best unre-ranked retrieval baseline**  
* BM25 remains the reference baseline, but the final comparison should also include the strongest Phase 2 retrieval mode   
* comparison is fair and reproducible  
* final chosen model can be traced back to params, metrics, artifacts, and data version  
* final model choice is justified with evidence  
* at least one experiment compares the project’s default graded mapping against the Amazon-style compressed gain mapping

MLflow Tracking is meant to capture these experiment artifacts during the run, not afterward.

---

## **Phase 5 — Optional reranking**

### **Objective**

Test whether a late-stage reranker is worth it.

### **Build**

* rerank top-N only  
* benchmark top-10, top-20, top-50  
* use a small cross-encoder only if local inference is practical

### **Required analysis**

Produce a strict **quality-vs-latency graph**:

* x-axis: added latency  
* y-axis: NDCG@10 / MRR lift

OpenSearch supports reranking through a rerank processor in a search pipeline. ([OpenSearch Documentation](https://docs.opensearch.org/latest/search-plugins/search-relevance/reranking-search-results/?utm_source=chatgpt.com))

### **Decision rule**

Adopt reranking only if:

* quality lift is meaningful  
* end-to-end P95 remains acceptable  
* the local serving path remains practical

### **Acceptance criteria**

* reranking recommendation is evidence-based  
* no reranking is allowed to remain the final answer if it is not worth the latency

---

## **Phase 6 — Production-style API and latency budget enforcement**

### **Objective**

Turn the system into a service.

### **Endpoints**

* `GET /search`  
* `GET /debug/search`  
* `GET /health`  
* `GET /explain`

OpenSearch supports explain-style inspection and hybrid explanation, which is useful for debugging ranking behavior. ([OpenSearch Documentation](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/explain/?utm_source=chatgpt.com))

### **Build**

* timeouts  
* request IDs  
* structured logs  
* latency timing per stage  
* fallback paths  
* basic caching only if needed

### **Fallback rules**

* reranker too slow → skip rerank  
* feature generation timeout → use retrieval order or simpler scorer  
* OpenSearch issue on advanced path → safe baseline response

### **Acceptance criteria**

* P95 is measured, not guessed  
* fallback paths are testable  
* API behaves predictably under degradation

---

## **Phase 7 — Failure analysis and portfolio packaging**

### **Objective**

Make the project interview-ready.

### **Build**

* failure taxonomy  
* query bucket analysis  
* before/after examples  
* latency dashboard  
* architecture diagram  
* concise README \+ deep-dive docs

### **Outputs**

* portfolio-quality repo  
* experiment summary table  
* screenshots and diagrams  
* lessons-learned writeup

### **Acceptance criteria**

* a recruiter understands the project in under 60 seconds  
* a technical interviewer can drill into ranking, evaluation, and system tradeoffs

## **13\. Data modeling decisions**

### **Search document**

Each indexed product document should include:

* product id  
* title  
* concatenated searchable text  
* brand  
* color  
* locale  
* optional categorical fields  
* stored attributes for explanation/debug

### **Relevance mapping**

Default graded relevance mapping for ranking metrics:

* Exact \= 3  
* Substitute \= 2  
* Complement \= 1  
* Irrelevant \= 0

This is the **primary project mapping** because it is easier to interpret, easier to debug visually, and aligns well with graded relevance analysis for NDCG-style evaluation.

This is a **deliberate product choice**, not a universal truth. In this project, **Complement** is treated as a weak positive signal because product search can reasonably benefit from retrieving related accessories or add-on items in lower-ranked positions.

The Amazon baseline ranking script uses a more compressed gain scale:

* Exact \= 1.0  
* Substitute \= 0.1  
* Complement \= 0.01  
* Irrelevant \= 0.0

For this project, that compressed mapping will be treated as a **Phase 4 experimental variation**, not the default. This allows us to test whether gain scaling meaningfully changes model behavior, feature importance, and final ranking quality.

Planned gain-mapping sensitivity checks:

* Default mapping: `E=3, S=2, C=1, I=0`  
* Stricter mapping: `E=3, S=2, C=0, I=0`  
* Amazon-style compressed mapping: `E=1.0, S=0.1, C=0.01, I=0.0`

Amazon’s official ESCI dataset defines the four labels as **Exact, Substitute, Complement, and Irrelevant**; the numeric gain mapping is your ranking-policy choice. 

## **14\. Risk register**

### **Risk 1**

**Dataset is larger than ideal for local iteration**  
Mitigation:

* start with US-only reduced version  
* use smaller dev slice during rapid iteration  
* run full local benchmark less frequently  
* verify that Git LFS parquet assets are fully fetched before full preprocessing and indexing runs 

### **Risk 2**

**OpenSearch \+ MLflow \+ API stack feels heavy locally or causes Mac Mini memory exhaustion**

Mitigation:

* single-node Docker Compose only  
* one-command startup  
* no unnecessary services  
* **enforce explicit JVM heap limits in `docker-compose.yml` using `OPENSEARCH_JAVA_OPTS`**  
* start with a local-safe heap such as:  
  * `-Xms1g -Xmx1g`  
  * or `-Xms512m -Xmx512m` for lighter iteration  
* document the Docker Desktop memory allocation requirement and keep the stack intentionally small during early development  
* separate embedding generation from indexing to avoid recomputation after crashes  
* explicitly reserve and document local ports for OpenSearch, MLflow, and FastAPI

OpenSearch’s Docker docs and settings docs explicitly show `OPENSEARCH_JAVA_OPTS` heap control and examples like `-Xms512m -Xmx512m`

### **Risk 3**

**Reranking is too slow on the Mac mini**  
Mitigation:

* keep reranking optional  
* benchmark top-10/top-20 first  
* allow no-rerank final architecture

### **Risk 4**

**Feature engineering balloons in scope**  
Mitigation:

* define a fixed feature budget early  
* prioritize high-value lexical/product features first

## **15\. Repo structure**

amazon-esci-search-platform/  
├── README.md  
├── docker-compose.yml  
├── pyproject.toml  
├── .env.example  
├── configs/  
|     |---- local\_ports.yaml / services. yaml  
├── data/  
│   ├── raw/  
│   ├── processed/  
|     |	|--embeddings/  
│   └── evaluation/  
├── src/  
│   ├── data\_prep/  
│   ├── indexing/  
│   ├── retrieval/  
│   ├── features/  
│   ├── ranking/  
│   ├── api/  
│   ├── evaluation/  
│   └── common/  
├── scripts/  
│   ├── prepare\_data.py  
│   ├── build\_index.py  
│   ├── run\_eval.py  
│   ├── train\_ranker.py  
│   └── benchmark\_latency.py  
├── tests/  
├── docs/  
 |    |-- local\_setup.md  
└── assets/

## **16\. Final definition of success**

This project is successful if, by the end, you have:

* one clean ESCI-based **BM25 \+ vector \+ hybrid retrieval pipeline**  
* one reproducible evaluation setup  
* one defensible LTR comparison:  
  * pointwise  
  * pairwise  
  * listwise  
* one measured latency budget  
* one production-style search API  
* one clear explanation of when reranking is or is not worth it  
* one strong portfolio artifact that demonstrates end-to-end MLE/system-design thinking

This is now a solid, realistic, zero-budget PRD anchored to a public dataset you can actually access today. ([Amazon Science](https://www.amazon.science/code-and-datasets/shopping-queries-dataset-a-large-scale-esci-benchmark-for-improving-product-search))

