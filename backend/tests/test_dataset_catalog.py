from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.research.events import DatasetManifest, EventDatasetCatalog


def manifest(dataset_id: str, *, parts: list[str], exchanges: list[str] | None = None) -> DatasetManifest:
    now = datetime.now(timezone.utc)
    return DatasetManifest(
        dataset_id=dataset_id,
        created_at=now,
        updated_at=now,
        parts=parts,
        exchanges=exchanges or [],
    )


@pytest.mark.parametrize("dataset_id", ["../escape", "nested/path", " space", "", "a" * 129])
def test_dataset_ids_fail_closed(dataset_id, tmp_path):
    catalog = EventDatasetCatalog(tmp_path)

    with pytest.raises(ValueError, match="Invalid dataset id"):
        catalog.get(dataset_id)


def test_legacy_manifests_derive_exchanges_from_partition_paths(tmp_path):
    catalog = EventDatasetCatalog(tmp_path)
    catalog._save_manifest(
        manifest(
            "legacy-dataset",
            parts=[
                "exchange=bybit/symbol=BTC/date=2026-08-03/part.parquet",
                "exchange=hyperliquid/symbol=BTC/date=2026-08-03/part.parquet",
            ],
        )
    )

    assert catalog.get("legacy-dataset").exchanges == ["bybit", "hyperliquid"]


def test_dataset_reader_rejects_manifest_path_traversal(tmp_path):
    catalog = EventDatasetCatalog(tmp_path)
    catalog._save_manifest(manifest("unsafe-dataset", parts=["../outside.parquet"]))

    with pytest.raises(ValueError, match="invalid part path"):
        catalog.read("unsafe-dataset")
