from __future__ import annotations

from data_prep.prepare import _stable_query_sample


def test_stable_query_sample_is_deterministic() -> None:
    query_ids = [5, 1, 9, 2, 7, 3]
    sample_a = _stable_query_sample(query_ids, 3)
    sample_b = _stable_query_sample(query_ids, 3)
    assert sample_a == sample_b
    assert len(sample_a) == 3
