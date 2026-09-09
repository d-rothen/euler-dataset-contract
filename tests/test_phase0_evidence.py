"""Check shared evidence without loading NumPy, Torch, or any consumer package."""

from __future__ import annotations

import math
import re
import runpy
from pathlib import Path

import pytest

from euler_dataset_contract.testing import EvidenceCase, corpus


def _multiply(a, b):
    return [
        [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(len(b[0]))]
        for i in range(3)
    ]


def test_evidence_manifest_and_payload_agree(evidence_case) -> None:
    case = evidence_case
    assert isinstance(case, EvidenceCase)
    assert case.payload["contract"] == {"kind": "phase0_evidence", "version": "1.0"}
    assert case.payload["name"] == case.name
    assert case.payload["kind"] == case.kind
    assert case.payload["description"] == case.description
    assert case.description.strip()


def test_evidence_covers_the_phase0_boundaries(evidence_cases) -> None:
    assert {case.kind for case in evidence_cases} == {
        "preprocessing",
        "backend",
        "geometry",
        "projection",
        "calibration",
        "alignment",
        "decoding",
        "persistence",
    }
    assert len({case.name for case in evidence_cases}) == len(evidence_cases)


def test_evidence_readers_reject_typos_and_return_detached_values() -> None:
    with pytest.raises(ValueError, match="Unknown evidence kind"):
        corpus.evidence_cases("preprocesing")
    first = corpus.evidence_cases("preprocessing")
    first[0].payload["inputs"].clear()
    assert corpus.evidence_cases("preprocessing")[0].payload["inputs"]
    observed = corpus.loader_observations()
    observed["observations"].clear()
    assert corpus.loader_observations()["observations"]


def test_five_field_examples_have_independent_pixel_references() -> None:
    for case in corpus.evidence_cases("preprocessing"):
        data = case.payload
        assert set(data["inputs"]) == {
            "rgb",
            "depth",
            "valid_mask",
            "intrinsics",
            "ray_map",
        }
        h, w = data["config"]["resize"]
        ch, cw = data["config"]["crop"]["size"]
        assert data["reference"]["crop_box"] == [(h - ch) // 2, (w - cw) // 2, ch, cw]
        for probe in data["reference"].get("probes", []):
            y, x = probe["at"]
            top, left, _, _ = data["reference"]["crop_box"]
            source_h, source_w = data["source_size"]
            source_x = (x + left + 0.5) * source_w / w - 0.5
            source_y = (y + top + 0.5) * source_h / h - 0.5
            assert [source_x, source_y] == pytest.approx(probe["source_xy"])
            offset, cy, cx = data["inputs"]["depth"]["coefficients"]
            assert offset + cy * source_y + cx * source_x == pytest.approx(
                probe["depth"]
            )


def test_intrinsics_answers_preserve_projection_geometry() -> None:
    for entry in corpus.evidence_cases("geometry")[0].payload["cases"]:
        source_h, source_w = entry["source_size"]
        height, width = entry["resize"] or entry["source_size"]
        sx, sy = width / source_w, height / source_h
        top, left, _, _ = entry["crop_box"]
        image_transform = [
            [sx, 0, (sx - 1) / 2 - left],
            [0, sy, (sy - 1) / 2 - top],
            [0, 0, 1],
        ]
        expected = _multiply(image_transform, entry["K_in"])
        for row, reference in zip(expected, entry["K_out"]):
            assert row == pytest.approx(reference)
        projected = _multiply(expected, [[v] for v in entry["point"]])
        pixel = [projected[i][0] / projected[2][0] for i in (0, 1)]
        assert pixel == pytest.approx(entry["pixel"])


def test_dense_xyz_reference_reprojects_to_its_source_pixels() -> None:
    data = corpus.evidence_cases("projection")[0].payload
    for y, row in enumerate(data["point_map_hwc"]):
        for x, point in enumerate(row):
            projected = _multiply(data["K"], [[v] for v in point])
            assert [projected[i][0] / projected[2][0] for i in (0, 1)] == [x, y]
            assert point[2] == data["depth"][y][x]
            assert sum(v * v for v in point) == data["radial_squared"][y][x]
            assert all(math.isfinite(v) for v in point)


def test_loader_snapshot_classifies_each_declaration(loader_observations) -> None:
    snapshot = loader_observations
    assert snapshot["provenance"]["consumed_by_runtime"] is False
    seen = set()
    for entry in snapshot["observations"]:
        key = (entry["loader"], entry["function"], entry["backend"])
        assert key not in seen, key
        seen.add(key)
        assert entry["backend"] in {"cpu", "gpu"}
        assert entry["source"] in snapshot["sources"]
        assert re.fullmatch(r"[0-9a-f]{64}", snapshot["sources"][entry["source"]])
        assert {"modality_type", "dtype", "shape"} <= entry["declared"].keys()
    declared_pairs = {(loader, function) for loader, function, _ in seen}
    catalog_pairs = {
        (loader["name"], entry["function"])
        for loader in snapshot["catalog"]
        for entry in loader["modalities"]
    }
    assert declared_pairs == catalog_pairs
    assert len(seen) == 2 * len(catalog_pairs)


def test_snapshot_extraction_reads_literals_without_executing_sources(tmp_path) -> None:
    script = (
        Path(__file__).resolve().parents[1] / "scripts/refresh_loader_observations.py"
    )
    snapshot = runpy.run_path(str(script))["snapshot"]
    loaders = tmp_path / "euler_loading/loaders"
    loaders.mkdir(parents=True)
    (loaders / "_constants.py").write_text(
        "UNIT = 'meters'\nraise RuntimeError('must not execute')\n"
    )
    for backend in ("cpu", "gpu"):
        folder = loaders / backend
        folder.mkdir()
        (folder / "demo.py").write_text(
            "from euler_loading.loaders._constants import UNIT\n"
            "@modality_meta(modality_type='depth', dtype='float32', shape='HW', output_unit=UNIT)\n"
            "def depth(path): raise RuntimeError('must not execute')\n"
        )
    (loaders / "generate").mkdir()
    (loaders / "generate/loaders.json").write_text('{"supportedLoaders": []}')
    result = snapshot(tmp_path)
    assert len(result["observations"]) == 2
    assert all(r["declared"]["output_unit"] == "meters" for r in result["observations"])
    assert "euler_loading/loaders/_constants.py" in result["sources"]
