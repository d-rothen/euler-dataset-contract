"""Numerical geometry and the current shape-only evaluator alignment."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from euler_eval.data import (
    align_intrinsics_to_prediction,
    align_to_prediction,
    classify_spatial_alignment,
    get_depth_metadata,
    project_point_cloud_to_depth_map,
    unproject_depth_to_points,
)
from euler_eval.metrics.utils import convert_planar_to_radial
from euler_loading import SamplePreprocessor

from euler_dataset_contract import build_default_meta

from ._support import evidence, make_sample


@pytest.mark.parametrize(
    "entry", evidence("legacy-spatial-alignment")["classifications"]
)
def test_current_shape_classification(entry):
    assert classify_spatial_alignment(*entry["gt"], *entry["pred"]) == entry["method"]


def test_current_resize_sampling_and_mask_dtype():
    entry = evidence("legacy-spatial-alignment")["small_resize"]
    gt = np.array(entry["gt"], dtype=np.float32)
    pred = np.zeros(entry["pred_size"], dtype=np.float32)
    np.testing.assert_array_equal(align_to_prediction(gt, pred), entry["observed"])
    mask = gt % 4 == 0
    aligned = align_to_prediction(mask, pred)
    np.testing.assert_array_equal(aligned, mask[::2, ::2])
    assert aligned.dtype == np.bool_


def test_current_crop_origin_and_camera_are_top_left():
    entry = evidence("legacy-spatial-alignment")["center_crop_ambiguity"]
    gt = np.arange(np.prod(entry["gt_size"]), dtype=np.float32).reshape(
        entry["gt_size"]
    )
    pred = gt[1:9, 1:9].copy()
    np.testing.assert_array_equal(align_to_prediction(gt, pred), gt[:8, :8])
    K = np.array(entry["K_in"])
    aligned_K = align_intrinsics_to_prediction(K, gt.shape, pred.shape)
    np.testing.assert_array_equal(aligned_K, entry["observed_K"])
    np.testing.assert_array_equal(K, entry["K_in"])
    assert not np.allclose(aligned_K, entry["reference_K"])


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="eval-crop-origin: shape alone cannot recover center-crop offsets",
)
def test_center_cropped_prediction_matches_correct_ground_truth():
    entry = evidence("legacy-spatial-alignment")["center_crop_ambiguity"]
    K = align_intrinsics_to_prediction(
        np.array(entry["K_in"]), entry["gt_size"], entry["pred_size"]
    )
    np.testing.assert_array_equal(K, entry["reference_K"])


def test_documented_preprocessing_is_not_recoverable_from_final_shape():
    data = evidence("documented-five-field")
    sample = make_sample(data)
    prediction = SamplePreprocessor.from_config(data["config"])(sample)
    aligned = align_to_prediction(sample["depth"], prediction["depth"])
    aligned_K = align_intrinsics_to_prediction(
        sample["intrinsics"]["camera_0"],
        data["source_size"],
        data["reference"]["output_size"],
    )
    assert aligned.shape == prediction["depth"].shape
    assert not np.allclose(aligned, prediction["depth"])
    assert not np.allclose(aligned_K, prediction["intrinsics"])


def test_resize_intrinsics_scales_skew_and_preserves_source():
    entry = next(
        e for e in evidence("pinhole-projections")["cases"] if e.get("known_failure")
    )
    K = np.array(entry["K_in"], dtype=np.float64)
    aligned = align_intrinsics_to_prediction(K, entry["source_size"], entry["resize"])
    top, left, _, _ = entry["crop_box"]
    aligned[0, 2] -= left
    aligned[1, 2] -= top
    np.testing.assert_allclose(aligned, entry["K_out"])
    np.testing.assert_array_equal(K, entry["K_in"])


@pytest.mark.parametrize("radial", [False, True], ids=["planar", "radial"])
def test_known_depth_unprojection_and_cloud_projection(radial):
    data = evidence("depth-projection")
    K = np.array(data["K"], dtype=np.float64)
    planar = np.array(data["depth"], dtype=np.float32)
    radius = np.sqrt(data["radial_squared"])
    depth = radius if radial else planar
    points = unproject_depth_to_points(depth, K, depth_is_radial=radial)
    np.testing.assert_allclose(points, data["point_map_hwc"], rtol=0, atol=data["atol"])
    projected, mask, stats = project_point_cloud_to_depth_map(
        points.reshape(-1, 3), K, np.eye(4), planar.shape
    )
    np.testing.assert_allclose(projected, radius, rtol=0, atol=data["atol"])
    assert mask.all() and stats["projected_pixels"] == planar.size
    intrinsic_values = {"fx": K[0, 0], "fy": K[1, 1], "cx": K[0, 2], "cy": K[1, 2]}
    np.testing.assert_allclose(
        convert_planar_to_radial(planar, intrinsic_values),
        radius,
        rtol=0,
        atol=data["atol"],
    )


def test_depth_defaults_currently_disagree():
    data = evidence("legacy-spatial-alignment")["defaults"]
    # Only a legacy/unchecked metadata provider can omit this required core field.
    dataset = SimpleNamespace(get_modality_metadata=lambda key: {})
    assert build_default_meta("depth")["radial_depth"] == data["contract_radial_depth"]
    assert get_depth_metadata(dataset)["radial_depth"] == data["eval_radial_depth"]
