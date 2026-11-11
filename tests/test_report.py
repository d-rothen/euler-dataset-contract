"""The modality vocabulary report and ``python -m euler_dataset_contract``."""

from __future__ import annotations

import json
import subprocess
import sys

from euler_dataset_contract import build_meta_schema, inventory, modality_report
from euler_dataset_contract.__main__ import main


def test_inventory_is_a_detached_copy() -> None:
    first = inventory()
    first["aliases"]["rgb"]["id"] = "changed"
    assert inventory()["aliases"]["rgb"]["id"] == "appearance.camera.color"
    assert inventory()["contract"] == {"kind": "modality_inventory", "version": "1.0"}


def test_report_carries_inventory_meta_schema_and_version() -> None:
    report = modality_report()
    assert report["contract"] == {"kind": "modality_vocabulary_report", "version": "1.0"}
    assert report["package"]["name"] == "euler-dataset-contract"
    assert "version" in report["package"]
    assert report["inventory"] == inventory()
    assert report["modality_meta_schema"] == build_meta_schema()
    assert "modality_meta_schema" not in modality_report(include_meta_schema=False)
    json.dumps(report)  # JSON-ready


def test_cli_inventory(capsys) -> None:
    assert main(["inventory", "--no-meta-schema"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["inventory"]["aliases"]["normals"]["id"] == "geometry.camera.surface_normals"
    assert "modality_meta_schema" not in payload


def test_cli_resolve(capsys) -> None:
    assert main(["resolve", "flow", "calibration", "unknown_thing"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["flow"]["modality_id"] == "geometry.camera.optical_flow"
    assert payload["calibration"]["status"] == "non_modality"
    assert payload["unknown_thing"]["status"] == "unknown"


def test_module_entry_point() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "euler_dataset_contract", "inventory"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["contract"]["kind"] == "modality_vocabulary_report"
