from __future__ import annotations


def product_index_mapping(embedding_dimension: int) -> dict[str, object]:
    return {
        "settings": {
            "index": {
                "knn": True,
                "number_of_shards": 1,
                "number_of_replicas": 0,
            }
        },
        "mappings": {
            "properties": {
                "document_id": {"type": "keyword"},
                "product_id": {"type": "keyword"},
                "product_locale": {"type": "keyword"},
                "product_title": {"type": "text"},
                "product_brand": {"type": "keyword"},
                "product_color": {"type": "keyword"},
                "product_description": {"type": "text"},
                "product_bullet_point": {"type": "text"},
                "product_text": {"type": "text"},
                "searchable_text": {"type": "text"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": embedding_dimension,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                    },
                },
            }
        },
    }
