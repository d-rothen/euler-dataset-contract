"""Execute Phase 0 examples against euler-loading; no behavior is changed."""

from __future__ import annotations

import copy
import importlib

import numpy as np
import pytest
from ds_crawler import index_dataset_from_path
from euler_loading import Crop, SamplePreprocessor, crop_intrinsics, resize_intrinsics
from euler_loading import preprocessing as pp
from PIL import Image

from euler_dataset_contract import parse_dataset_head
from euler_dataset_contract.testing import evidence_case_params

from ._support import (
    as_numpy,
    assert_preprocessed,
    evidence,
    golden,
    make_dataset,
    make_sample,
    reload_dataset,
)


@pytest.mark.parametrize("case", evidence_case_params("preprocessing"))
@pytest.mark.parametrize("tensors", [False, True], ids=["numpy-via-torch", "torch-cpu"])
def test_five_field_preprocessing(case, tensors):
    original = make_sample(case.payload, tensors=tensors)
    before = copy.deepcopy(original)
    output = SamplePreprocessor.from_config(case.payload["config"])(original)
    assert_preprocessed(output, case.payload)
    for key in original:
        if key == "intrinsics":
            for sensor in original[key]:
                np.testing.assert_array_equal(
                    as_numpy(original[key][sensor]), as_numpy(before[key][sensor])
                )
        else:
            np.testing.assert_array_equal(
                as_numpy(original[key]), as_numpy(before[key])
            )


@pytest.mark.parametrize(
    "entry", evidence("pinhole-projections")["cases"], ids=lambda e: e["name"]
)
def test_crop_boxes_and_current_intrinsics(entry):
    current_size = entry["resize"] or entry["source_size"]
    box = Crop.from_config(entry["crop"]).resolve_box(tuple(current_size))
    assert list(box) == entry["crop_box"]
    matrix = np.array(entry["K_in"], dtype=np.float64)
    if entry["resize"]:
        matrix = resize_intrinsics(
            matrix, source_size=entry["source_size"], target_size=entry["resize"]
        )
    matrix = crop_intrinsics(matrix, top=box[0], left=box[1])
    np.testing.assert_allclose(
        matrix, entry["K_out"], rtol=0, atol=1e-6
    )


def test_loading_intrinsics_agree_with_nonzero_skew_projection():
    entry = next(
        e for e in evidence("pinhole-projections")["cases"] if e.get("known_failure")
    )
    matrix = resize_intrinsics(
        np.array(entry["K_in"], dtype=np.float64),
        source_size=entry["source_size"],
        target_size=entry["resize"],
    )
    top, left, _, _ = entry["crop_box"]
    np.testing.assert_allclose(
        crop_intrinsics(matrix, top=top, left=left), entry["K_out"], rtol=0, atol=1e-6
    )


@pytest.mark.parametrize("entry", evidence("pinhole-projections")["invalid_crops"])
def test_invalid_crops_fail(entry):
    with pytest.raises(ValueError):
        Crop.from_config(entry["crop"]).resolve_box(entry["source_size"])


@pytest.mark.parametrize("backend", ["torch_cpu", "pillow"])
def test_legacy_backend_differences_are_explicit(backend, monkeypatch):
    data = evidence("backend-resize")
    if backend == "pillow":
        monkeypatch.setattr(pp, "torch", None)
        monkeypatch.setattr(pp, "F", None)
    sample = {
        "image": np.array(data["inputs"]["image"], dtype=np.float32),
        "mask": np.array(data["inputs"]["mask"], dtype=bool),
    }
    result = SamplePreprocessor.from_config(data["config"])(sample)
    for name, expected in data["observed"][backend].items():
        np.testing.assert_allclose(result[name], expected, rtol=0, atol=data["atol"])


def test_invalid_depth_is_currently_blended():
    data = evidence("invalid-depth")
    result = SamplePreprocessor.from_config(data["config"])(
        {
            "depth": np.array(data["inputs"]["depth"], dtype=np.float32),
            "valid_mask": np.array(data["inputs"]["valid_mask"], dtype=bool),
        }
    )
    for name, expected in data["observed"].items():
        np.testing.assert_array_equal(result[name], expected)
    assert float(result["depth"][0, 0]) != data["reference_valid_only_mean"]


def test_hierarchical_reduction_is_lexical_and_preserves_cached_sources():
    data = evidence("hierarchy-selection")
    calibrations = {
        key: np.array(value, dtype=np.float32)
        for key, value in data["calibrations"].items()
    }
    before = copy.deepcopy(calibrations)
    processor = SamplePreprocessor.from_config(data["config"])
    for _ in range(2):
        sample = {
            "rgb": np.zeros((*data["source_size"], 3), dtype=np.float32),
            "intrinsics": calibrations,
        }
        output = processor(sample)
        np.testing.assert_allclose(output["intrinsics"], data["observed_K"])
        assert not np.allclose(output["intrinsics"], data["reference_K"])
    for key in calibrations:
        np.testing.assert_array_equal(calibrations[key], before[key])


@pytest.mark.parametrize("backend", ["cpu", "gpu"], ids=["numpy", "torch-on-cpu"])
def test_known_value_decoders(tmp_path, backend):
    data = evidence("known-values")
    vkitti = importlib.import_module(f"euler_loading.loaders.{backend}.vkitti2")
    generic = importlib.import_module(f"euler_loading.loaders.{backend}.generic")
    dense = importlib.import_module(
        f"euler_loading.loaders.{backend}.generic_dense_depth"
    )
    muses = importlib.import_module(f"euler_loading.loaders.{backend}.muses")

    for function in data["scalar_maps"]["loaders"]:
        map_path = tmp_path / (function + ".npy")
        raw_map = np.array(data["scalar_maps"]["raw"], dtype=np.float64)
        np.save(map_path, raw_map)
        decoded = as_numpy(getattr(generic, function)(str(map_path)))
        assert decoded.dtype == np.float32
        np.testing.assert_array_equal(decoded, raw_map)
    label_path = tmp_path / "labels.npy"
    np.save(label_path, np.array(data["class_ids"]["raw"], dtype=np.uint8))
    labels = as_numpy(generic.semantic_segmentation(str(label_path)))
    assert labels.dtype == np.uint8
    np.testing.assert_array_equal(labels, data["class_ids"]["raw"])
    K = np.array(evidence("depth-projection")["K"], dtype=np.float64)
    K_path = tmp_path / "intrinsics.npy"
    np.save(K_path, K)
    decoded_K = as_numpy(generic.intrinsics(str(K_path)))
    assert decoded_K.dtype == np.float32
    np.testing.assert_array_equal(decoded_K, K)

    path = tmp_path / "depth.png"
    raw = np.array(data["depth"]["raw"], dtype=np.uint16)
    Image.fromarray(raw).save(path)
    depth = as_numpy(vkitti.depth(str(path), {"scale_to_meters": 0.01}))
    assert depth.shape == ((2, 3) if backend == "cpu" else (1, 2, 3))
    assert depth.dtype == np.float32
    np.testing.assert_allclose(
        depth.reshape(2, 3),
        data["depth"]["declared_centimeters"]["expected_meters"],
        rtol=0,
        atol=data["depth"]["atol"],
    )
    # Generic depth has a working per-file override, separate from head metadata.
    generic_depth = as_numpy(
        dense.depth(str(path), attributes={"scale_to_meters_override": 0.001})
    )
    np.testing.assert_allclose(
        generic_depth.reshape(2, 3),
        data["depth"]["declared_millimeters"]["expected_meters"],
        rtol=0,
        atol=data["depth"]["atol"],
    )

    for name in ("rgb", "palette"):
        pixels = np.array(data[name]["raw"], dtype=np.uint8)
        image_path = tmp_path / (name + ".png")
        Image.fromarray(pixels).save(image_path)
        function = vkitti.rgb if name == "rgb" else vkitti.class_segmentation
        value = as_numpy(function(str(image_path)))
        assert value.shape == ((2, 4, 3) if backend == "cpu" else (3, 2, 4))
        assert value.dtype == (np.float32 if name == "rgb" else np.int64)
        logical = value if backend == "cpu" else value.transpose(1, 2, 0)
        np.testing.assert_allclose(
            logical,
            pixels * (data["rgb"]["scale"] if name == "rgb" else 1),
            rtol=0,
            atol=1e-7,
        )

    cloud = np.array(data["cloud"]["raw"], dtype=np.float64)
    cloud_path = tmp_path / "cloud.bin"
    cloud.tofile(cloud_path)
    decoded = as_numpy(muses.sparse_depth(str(cloud_path)))
    assert decoded.dtype == np.float64
    np.testing.assert_array_equal(decoded, cloud)

    arbitrary = np.arange(40, dtype=np.float32).reshape(5, 2, 4)
    map_path = tmp_path / "map.npy"
    np.save(map_path, arbitrary)
    np.testing.assert_array_equal(
        as_numpy(generic.map_3d(str(map_path))),
        arbitrary.transpose(1, 2, 0) if backend == "cpu" else arbitrary,
    )
    points = arbitrary[:3].copy()
    np.save(map_path, points)
    np.testing.assert_array_equal(as_numpy(generic.points_3d(str(map_path))), points)
    np.testing.assert_array_equal(
        as_numpy(generic.atmospheric_light(str(map_path))),
        points.transpose(1, 2, 0) if backend == "cpu" else points,
    )
    rays = np.broadcast_to(
        np.array(data["ray_map"]["stored_direction"], dtype=np.float32)[:, None, None],
        (3, 2, 4),
    ).copy()
    np.save(map_path, rays)
    np.testing.assert_array_equal(
        as_numpy(generic.spherical_map(str(map_path))),
        rays.transpose(1, 2, 0) if backend == "cpu" else rays,
    )


@pytest.mark.parametrize("module", ["vkitti2", "generic_dense_depth"])
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="loader-ignores-head-scale: decoded units ignore scale_to_meters",
)
def test_head_scale_controls_decoded_metric_values(tmp_path, module):
    data = evidence("known-values")["depth"]
    path = tmp_path / "millimeters.png"
    Image.fromarray(np.array(data["raw"], dtype=np.uint16)).save(path)
    loader = importlib.import_module(f"euler_loading.loaders.cpu.{module}")
    decoded = loader.depth(str(path), {"scale_to_meters": 0.001})
    np.testing.assert_allclose(
        decoded,
        data["declared_millimeters"]["expected_meters"],
        rtol=0,
        atol=data["atol"],
    )


@pytest.mark.parametrize("zip_output", [False, True], ids=["directory", "zip"])
@pytest.mark.parametrize("scope", [None, "rgb"], ids=["unscoped", "scoped"])
def test_written_preprocessing_currently_keeps_source_head(tmp_path, zip_output, scope):
    processor = SamplePreprocessor.from_config(
        {
            "crop": {"size": [2, 4]},
            "fields": {"rgb": {"kind": "image", "layout": "HWC"}},
            "infer_fields": False,
        }
    )
    dataset, head, _ = make_dataset(tmp_path / "source", transforms=[processor])
    target = tmp_path / ("output.zip" if zip_output else "output")
    writer = dataset.create_output_writer(
        "rgb", target, zip=zip_output, metadata_scope=scope
    )
    sample = dataset[0]
    assert sample["rgb"].shape == (2, 4, 3)
    dataset.write_sample(0, {"rgb": sample["rgb"]}, writer)
    writer.save_index(filename="index.json")
    reloaded = reload_dataset(target, scope=scope)
    np.testing.assert_array_equal(reloaded[0]["rgb"], sample["rgb"])
    persisted = index_dataset_from_path(target, metadata_scope=scope)["head"]
    assert (
        persisted["modality"]["meta"]["dimensions"]
        == head["modality"]["meta"]["dimensions"]
    )
    assert "euler_transforms" not in persisted["addons"]
    assert (
        persisted["addons"]["phase0_annotations"]
        == head["addons"]["phase0_annotations"]
    )
    assert dataset.get_modality_index("rgb")["head"] == head


def test_loading_addon_rejects_unversioned_preprocessors_field():
    head = golden("phase0-opaque-annotations")
    head["addons"]["euler_loading"] = {"version": "1.0", "preprocessors": []}
    with pytest.raises(ValueError, match="Unknown.*preprocessors"):
        parse_dataset_head(head)
