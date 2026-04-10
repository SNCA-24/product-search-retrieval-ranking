from __future__ import annotations

from common.text import lexical_overlap_score, tokenize, unique_join


def test_tokenize_lowercases_and_strips_punctuation() -> None:
    assert tokenize("Pink Running Shoes!") == ["pink", "running", "shoes"]


def test_tokenize_handles_null_like_values() -> None:
    assert tokenize(None) == []
    assert tokenize(float("nan")) == []


def test_unique_join_deduplicates_empty_parts() -> None:
    assert unique_join(["Title", "", "Title", "Brand"]) == "Title\nBrand"


def test_lexical_overlap_rewards_overlap() -> None:
    better = lexical_overlap_score("wireless mouse", "wireless gaming mouse")
    worse = lexical_overlap_score("wireless mouse", "kitchen towel set")
    assert better > worse
