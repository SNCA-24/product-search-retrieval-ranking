from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from types import SimpleNamespace

import retrieval.service as retrieval_service
from retrieval.service import OpenSearchRetriever


def test_embedding_model_initialization_is_thread_safe(monkeypatch) -> None:
    created: list[object] = []
    created_lock = Lock()

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, device: str) -> None:
            assert model_name == "sentence-transformers/all-MiniLM-L6-v2"
            assert device == "cpu"
            with created_lock:
                created.append(self)

    fake_module = SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setattr(retrieval_service, "require_optional", lambda *args, **kwargs: fake_module)

    retriever = OpenSearchRetriever(
        settings=SimpleNamespace(
            resolved_profile=lambda profile: profile,
            models={"embeddings": {"name": "sentence-transformers/all-MiniLM-L6-v2"}},
        ),
        profile="full",
    )

    with ThreadPoolExecutor(max_workers=4) as pool:
        instances = list(pool.map(lambda _: retriever._embedding_model_instance(), range(4)))

    assert len(created) == 1
    assert len({id(instance) for instance in instances}) == 1
