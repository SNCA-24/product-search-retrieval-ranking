# Local Setup

This project is tuned for a 16 GB Apple Silicon Mac Mini. The goal is to keep the machine responsive and avoid turning local setup into a system-wide dependency tangle.

## 1. Python first

Use a clean project-local interpreter, not the Anaconda base interpreter.

Preferred local runtime:

- Python `3.12`

Also supported:

- Python `3.11`

If you already have Homebrew `3.12`, use it directly:

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

If you need to install it:

```bash
brew install python@3.12 libomp
```

Install only the light Phase 0/1 dependencies first:

```bash
pip install -e ".[dev]"
```

Run the local health check:

```bash
python scripts/doctor.py --profile dev
```

## 2. Data paths

The raw dataset already lives outside `data/raw/`:

- `esci-data-main/shopping_queries_dataset/data/esci_train.parquet`
- `esci-data-main/shopping_queries_dataset/data/esci_test.parquet`
- `esci-data-main/shopping_queries_dataset/shopping_queries_dataset_sources.csv`

Do not copy these files again. Update `configs/services.yaml` only if the paths change.

## 3. Phase 1 workflow

Generate the canonical processed dev slice and offline evaluation artifacts:

```bash
python scripts/prepare_data.py --profile dev
python scripts/run_eval.py --profile dev --system baseline --split test --gain-mapping default
```

When you are ready for the full local slice:

```bash
python scripts/prepare_data.py --profile full
```

## 4. Phase 2 container runtime

Do not install Docker Desktop during Phase 0 or Phase 1.

When OpenSearch is needed, install a lightweight Docker-compatible runtime:

```bash
brew install colima docker docker-compose
colima start --cpu 2 --memory 4 --disk 20 --arch aarch64
```

Start only the OpenSearch service:

```bash
docker-compose up -d opensearch
```

Stop it when you are done:

```bash
docker-compose stop opensearch
```

The Compose file uses a single node, no dashboards, and `OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m`.

## 5. Retrieval and ranking dependencies

Install retrieval packages only when you start Phase 2:

```bash
pip install -e ".[retrieval,dev]"
```

Install ranking packages only when you start Phase 4:

```bash
pip install -e ".[retrieval,ranking,dev]"
```

This staged install pattern keeps the machine lighter during earlier phases.

## 6. API, UI, and screenshots

Run the full-profile API and UI on the host:

```bash
ESCI_PROFILE=full PYTHONPATH=src .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Then open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

The root page `/` is the search console used for:

- hybrid live serving demos
- online `ltr` inspection
- compare-drawer screenshots
- qualitative failure analysis

## 7. MLflow

Run MLflow on demand only:

```bash
mlflow ui --backend-store-uri ./mlruns --host 127.0.0.1 --port 5000
```

Do not leave MLflow or OpenSearch running in the background when you are not actively using them.

## 8. Docker Desktop fallback

If Colima becomes a blocker, Docker Desktop is the fallback.

Recommended limits:

- Memory: `4 GB`
- CPUs: `2`
- Disable auto-start at login
- Do not keep Dashboards or extra services running

Do not run Docker Desktop and Colima together.
