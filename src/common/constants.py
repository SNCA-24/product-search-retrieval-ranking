from __future__ import annotations

VALID_PROFILES = {"dev", "full"}
VALID_GAIN_MAPPINGS = {"default", "strict", "amazon"}
VALID_SYSTEMS = {"baseline", "bm25", "vector", "hybrid", "ltr"}

TEXT_COLUMNS = [
    "product_title",
    "product_description",
    "product_bullet_point",
    "product_brand",
    "product_color",
    "product_text",
]

RAW_COLUMNS = [
    "example_id",
    "query",
    "query_id",
    "product_id",
    "product_locale",
    "esci_label",
    "small_version",
    "large_version",
    "product_title",
    "product_description",
    "product_bullet_point",
    "product_brand",
    "product_color",
    "product_text",
]

SEARCH_DOCUMENT_COLUMNS = [
    "document_id",
    "product_id",
    "product_locale",
    "product_title",
    "product_brand",
    "product_color",
    "product_description",
    "product_bullet_point",
    "product_text",
    "searchable_text",
]
