"""Real producer transforms and their source-backed directory/ZIP writer."""

from __future__ import annotations

import copy

import numpy as np
import pytest
from ds_crawler import index_dataset_from_path
from euler_preprocess.common.dataset import build_dataset
from euler_preprocess.common.intrinsics import extract_intrinsics
from euler_preprocess.common.output import prepare_output_backend
from euler_preprocess.radial.transform import RadialTransform

from ._support import as_numpy, evidence, file_entries, make_dataset, reload_dataset


@pytest.mark.parametrize("zip_output", [False, True], ids=["directory", "zip"])
def test_radial_transform_bytes_and_output_metadata(tmp_path, zip_output):
    data = evidence("depth-projection")
    dataset, head, _ = make_dataset(
        tmp_path / "source",
        modality="depth",
        values=np.array(data["depth"], dtype=np.float32),
    )
    target = tmp_path / ("radial.zip" if zip_output else "radial")
    backend = prepare_output_backend(
        {"output_path": str(target)}, dataset, RadialTransform
    )
    config_path = tmp_path / "radial.json"
    config_path.write_text("{}\n", encoding="utf-8")
    sample = dataset[0]
    sample["intrinsics"] = {"intrinsics": np.array(data["K"], dtype=np.float32)}
    before = copy.deepcopy(sample)
    paths = RadialTransform(str(config_path), str(target), output_backend=backend).run(
        [sample]
    )
    assert len(paths) == 1
    reloaded = reload_dataset(target, modality="depth")
    np.testing.assert_allclose(
        reloaded[0]["depth"], np.sqrt(data["radial_squared"]), rtol=0, atol=data["atol"]
    )
    persisted = index_dataset_from_path(target)
    expected = copy.deepcopy(head)
    expected["modality"]["meta"]["radial_depth"] = True
    assert persisted["head"] == expected
    assert file_entries(persisted)[0]["attributes"] == {"source_tag": "synthetic"}
    assert dataset.get_modality_index("depth")["head"] == head
    np.testing.assert_array_equal(
        sample["intrinsics"]["intrinsics"], before["intrinsics"]["intrinsics"]
    )
    np.testing.assert_array_equal(sample["depth"], before["depth"])


@pytest.mark.parametrize("zip_output", [False, True], ids=["directory", "zip"])
def test_producer_variant_ids_attributes_and_opaque_addon(tmp_path, zip_output):
    class CropWriterProbe:
        SOURCE_MODALITY = "depth"
        OUTPUT_SLOT = "depth"

    data = evidence("source-backed")
    dataset, head, values = make_dataset(tmp_path / "source", modality="depth")
    target = tmp_path / ("variants.zip" if zip_output else "variants")
    backend = prepare_output_backend(
        {"output_path": str(target)}, dataset, CropWriterProbe
    )
    # A probe of the existing public hook, without assigning replay semantics.
    annotation = {"version": "1.0", "description": "Phase 0 writer hook probe"}
    backend.add_head_addon("phase0_writer_probe", annotation)
    for variant in data["variants"]:
        y, x = variant["attributes"]["phase0_origin"]["offset"]
        backend.write(
            dataset[0],
            values[y : y + 2, x : x + 4],
            output_full_id=variant["full_id"],
            output_basename=variant["basename"],
            attributes=variant["attributes"],
        )
    backend.finalize()
    persisted = index_dataset_from_path(target)
    assert persisted["head"]["addons"]["phase0_writer_probe"] == annotation
    assert (
        persisted["head"]["addons"]["phase0_annotations"]
        == head["addons"]["phase0_annotations"]
    )
    variants = {v["basename"]: v for v in data["variants"]}
    for entry in file_entries(persisted):
        expected = variants[entry["path"].split("/")[-1]]
        assert entry["attributes"] == {
            "source_tag": "synthetic",
            **expected["attributes"],
        }
    reloaded = reload_dataset(target, modality="depth")
    assert len(reloaded) == 2
    for sample in reloaded:
        origin = sample["meta"]["depth"]["attributes"]["phase0_origin"]
        assert sample["full_id"] == next(
            v["full_id"]
            for v in data["variants"]
            if v["attributes"]["phase0_origin"]["variant_id"] == origin["variant_id"]
        )
        y, x = origin["offset"]
        np.testing.assert_array_equal(sample["depth"], values[y : y + 2, x : x + 4])
    assert dataset.get_modality_index("depth")["head"] == head


def test_dataset_builder_applies_shared_preprocessing_config(tmp_path):
    _, _, values = make_dataset(tmp_path / "source", modality="depth")
    config = {
        "modalities": {"depth": str(tmp_path / "source")},
        "preprocessing": {"crop": {"size": [2, 4]}},
    }
    dataset = build_dataset(config, {"depth"})
    # Loader resolution may choose Torch's 1HW output; the shared center crop
    # must still select the same source pixels.
    np.testing.assert_array_equal(
        as_numpy(dataset[0]["depth"]).reshape(2, 4), values[1:3, 2:6]
    )


def test_producer_calibration_requires_the_intrinsics_file_id():
    data = evidence("hierarchy-selection")
    calibrations = {k: np.array(v) for k, v in data["calibrations"].items()}
    assert extract_intrinsics({"intrinsics": calibrations}) is None
    K = calibrations[data["intended_camera"]]
    np.testing.assert_array_equal(
        extract_intrinsics({"intrinsics": {"intrinsics": K}}), K
    )
