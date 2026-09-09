"""An archive manifest must never silently refer to dropped evidence."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from euler_dataset_contract.testing import fixtures_root

VERIFY = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/verify_distribution.py")
)["_verify_corpus"]


@pytest.mark.parametrize("prefix", ["fixtures", "euler_dataset_contract/_fixtures"])
def test_archive_verification_reads_every_manifest_reference(prefix):
    files = {
        f"{prefix}/{path.relative_to(fixtures_root()).as_posix()}": path.read_bytes()
        for path in fixtures_root().rglob("*.json")
    }
    VERIFY(set(files), prefix, files.__getitem__)
    missing = f"{prefix}/preprocessing/documented-five-field.json"
    files.pop(missing)
    with pytest.raises(
        ValueError, match="missing manifest fixture.*documented-five-field"
    ):
        VERIFY(set(files), prefix, files.__getitem__)


def test_archive_verification_rejects_manifest_path_traversal():
    manifest = {
        "valid_heads": [],
        "invalid_heads": [],
        "inventory": [],
        "evidence": [{"path": "../outside.json"}],
    }
    with pytest.raises(ValueError, match="Unsafe archive path"):
        VERIFY(set(), "fixtures", lambda _: json.dumps(manifest).encode())
