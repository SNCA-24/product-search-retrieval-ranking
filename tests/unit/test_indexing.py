from __future__ import annotations

from indexing.opensearch import _resolve_start_row


def test_resolve_start_row_prefers_checkpoint_but_never_exceeds_live_count() -> None:
    start_row, source = _resolve_start_row(
        total_documents=1000,
        checkpoint={"next_row_index": 600, "source": "batch"},
        live_count=550,
        batch_size=250,
        bootstrap_from_live_count=False,
    )

    assert start_row == 500
    assert source == "checkpoint"


def test_resolve_start_row_bootstraps_from_live_count_on_batch_boundary() -> None:
    start_row, source = _resolve_start_row(
        total_documents=1000,
        checkpoint=None,
        live_count=630,
        batch_size=250,
        bootstrap_from_live_count=True,
    )

    assert start_row == 500
    assert source == "live_count_bootstrap"


def test_resolve_start_row_uses_live_count_for_synced_checkpoint() -> None:
    start_row, source = _resolve_start_row(
        total_documents=1000,
        checkpoint={"next_row_index": 500, "source": "live_count_sync"},
        live_count=880,
        batch_size=250,
        bootstrap_from_live_count=False,
    )

    assert start_row == 750
    assert source == "checkpoint"


def test_resolve_start_row_fresh_start_without_checkpoint_or_bootstrap() -> None:
    start_row, source = _resolve_start_row(
        total_documents=1000,
        checkpoint=None,
        live_count=630,
        batch_size=250,
        bootstrap_from_live_count=False,
    )

    assert start_row == 0
    assert source == "fresh"
