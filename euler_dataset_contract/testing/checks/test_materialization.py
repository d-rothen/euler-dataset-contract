"""Opt-in real generation/save/reload/replay conformance. No benchmark inputs."""

from __future__ import annotations

import numpy as np
import pytest
from ds_crawler import copy_dataset, read_record
from euler_loading import (
    CalibrationView,
    Modality,
    MultiModalDataset,
    replay_from_arrays,
)
from euler_preprocess.spatial import export_spatial

from euler_dataset_contract import resolve_receipt

from ._phase2_support import make_source
from ._support import assert_preprocessed


@pytest.mark.parametrize("archive", [False, True], ids=["directory", "zip"])
def test_actual_five_field_producer_and_replay(tmp_path, archive):
    source, descriptor, data, original = make_source(tmp_path / "source", count=1)
    config = {
        "modalities": {
            name: str(tmp_path / "source" / name)
            for name in descriptor["recipe"]["fields"]
            if name != "intrinsics"
        },
        "hierarchical_modalities": {"intrinsics": str(tmp_path / "source/intrinsics")},
        "preprocessing": data["config"],
        "bindings": {
            "fields": descriptor["recipe"]["fields"],
            "image_planes": descriptor["recipe"]["image_planes"],
            "revisions": {
                alias: record["revision"]
                for alias, record in descriptor["sources"].items()
            },
        },
        "outputs": {
            name: {
                "path": str(tmp_path / (name + (".zip" if archive else "_output"))),
                "dataset_id": "derived_" + name,
                "revision": "conformance_v1",
                "metadata_scope": "derived",
            }
            for name in descriptor["recipe"]["fields"]
        },
        "receipt_sidecars": True,
        "mapping": {"default": {"/scene_01/camera_0/frame_0": "/changed/frame/crop_a"}},
    }
    paths = export_spatial(config)
    result = {}
    receipts = {}
    for field, path in paths.items():
        dataset = MultiModalDataset({field: Modality(path, metadata_scope="derived")})
        sample = dataset[0]
        assert len(dataset) == 1 and sample["full_id"] == "/changed/frame/crop_a"
        result[field] = sample[field]
        receipts[field] = resolve_receipt(
            sample["attributes"][field]["euler_transforms"],
            lambda rel, root=path: read_record(root, rel, metadata_scope="derived"),
        )
        assert (
            dataset.get_modality_index(field)["head"]["addons"]["euler_transforms"][
                "plan"
            ]["field"]
            == field
        )
        np.testing.assert_array_equal(dataset[0][field], sample[field])
    assert_preprocessed(result, data)
    assert result["depth"][100, 200] == pytest.approx(2.981375, abs=1e-6)
    original["intrinsics"] = {
        "calibration": next(iter(original["intrinsics"].values()))
    }
    replayed = replay_from_arrays(descriptor, receipts["rgb"]["execution"], original)
    for field, value in result.items():
        np.testing.assert_array_equal(replayed[field], value)
    view = CalibrationView(descriptor, receipts["rgb"]["execution"], "intrinsics")
    np.testing.assert_array_equal(
        view.resolve(original["intrinsics"]["calibration"]), result["intrinsics"]
    )
    np.testing.assert_allclose(result["intrinsics"] @ [0, 0, 2], [639, 319, 2])
    copy_dataset(
        paths["rgb"],
        tmp_path / "relocated.zip",
        input_metadata_scope="derived",
        output_metadata_scope="moved",
    )
    relocated = MultiModalDataset(
        {"rgb": Modality(str(tmp_path / "relocated.zip"), metadata_scope="moved")}
    )
    np.testing.assert_array_equal(relocated[0]["rgb"], result["rgb"])
    # Original cached/source data retains its full plane and camera calibration.
    assert source[0]["rgb"].shape == (480, 960, 3)
    np.testing.assert_array_equal(
        source[0]["intrinsics"]["calibration"],
        [[800, 0, 479.5], [0, 800, 239.5], [0, 0, 1]],
    )
