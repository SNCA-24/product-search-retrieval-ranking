# Data Directory Policy

This repository keeps the `data/` directory in place for a consistent local project layout, but the heavy contents are intentionally not versioned.

What stays local-only:

- raw ESCI parquet files
- OpenSearch index data
- retrieval caches
- processed parquet outputs
- large run files and benchmark scratch artifacts
- local MLflow runs

What is kept in Git instead:

- lightweight `.gitkeep` markers where needed
- small human-readable summaries in `README.md` and `docs/`
- selected screenshots and report references

If you clone this repo, regenerate local artifacts with the documented scripts instead of expecting large data payloads to be present in Git.
