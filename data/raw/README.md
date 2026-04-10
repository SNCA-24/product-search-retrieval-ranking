# Raw Data Policy

Do not duplicate the ESCI parquet payloads into this repository.

The canonical raw inputs for this workspace already exist at:

- `esci-data-main/shopping_queries_dataset/data/esci_train.parquet`
- `esci-data-main/shopping_queries_dataset/data/esci_test.parquet`
- `esci-data-main/shopping_queries_dataset/shopping_queries_dataset_sources.csv`

If you need a local pointer under `data/raw/`, use a symlink or update `configs/services.yaml`.
