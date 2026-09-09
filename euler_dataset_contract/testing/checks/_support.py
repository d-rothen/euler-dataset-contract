"""Synthetic input construction for consumer checks, not transform execution."""

from __future__ import annotations

import copy

from euler_dataset_contract.testing import evidence_cases, golden_heads


def evidence(name):
    return next(case.payload for case in evidence_cases() if case.name == name)


def golden(name):
    return next(case.head for case in golden_heads() if case.name == name)


def as_numpy(value):
    import numpy as np

    return (
        value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)
    )


def make_sample(data, *, tensors=False):
    import numpy as np

    height, width = data["source_size"]
    yy, xx = np.indices((height, width), dtype=np.float64)
    result = {}
    for key, spec in data["inputs"].items():
        kind = spec["generator"]
        if kind == "affine_grid":
            coefficients = spec["coefficients"]
            multi = isinstance(coefficients[0], list)
            values = coefficients if multi else [coefficients]
            planes = [offset + cy * yy + cx * xx for offset, cy, cx in values]
            value = np.stack(planes, axis=-1) if multi else planes[0]
        elif kind == "rectangle":
            top, left, h, w = spec["box"]
            value = (yy >= top) & (yy < top + h) & (xx >= left) & (xx < left + w)
        elif kind == "constant":
            value = np.broadcast_to(
                spec["value"], (height, width, len(spec["value"]))
            ).copy()
        elif kind == "calibration":
            value = np.array(spec["value"], copy=True)
        else:
            raise ValueError(f"Unknown synthetic input generator: {kind}")
        value = np.asarray(value, dtype=spec["dtype"])
        if tensors:
            import torch

            value = torch.from_numpy(value)
        result[key] = {spec["key"]: value} if kind == "calibration" else value
    return result


def assert_preprocessed(values, data):
    import numpy as np

    expected = data["reference"]
    for key in ("rgb", "depth", "valid_mask", "ray_map"):
        assert list(as_numpy(values[key]).shape[:2]) == expected["output_size"]
    np.testing.assert_allclose(
        as_numpy(values["intrinsics"]),
        expected["intrinsics"],
        atol=expected["atol"],
        rtol=0,
    )
    for key in ("rgb", "depth", "valid_mask"):
        if key in expected:
            np.testing.assert_allclose(
                as_numpy(values[key]), expected[key], atol=expected["atol"], rtol=0
            )
    for probe in expected.get("probes", []):
        y, x = probe["at"]
        for key in ("rgb", "depth", "valid_mask"):
            np.testing.assert_allclose(
                as_numpy(values[key])[y, x], probe[key], atol=expected["atol"], rtol=0
            )
    rays = as_numpy(values["ray_map"])
    np.testing.assert_allclose(
        rays,
        np.broadcast_to(expected["ray_vector"], rays.shape),
        atol=expected["atol"],
        rtol=0,
    )
    assert as_numpy(values["valid_mask"]).dtype == np.bool_


def make_dataset(root, *, modality="rgb", transforms=None, scope=None, values=None):
    import numpy as np
    from ds_crawler import DatasetWriter
    from euler_loading import Modality, MultiModalDataset
    from euler_loading.loaders.cpu import generic_dense_depth

    head = golden("phase0-opaque-annotations")
    head["dataset"]["id"] = "source_" + modality
    head["modality"]["key"] = modality
    if modality == "depth":
        head["modality"]["meta"] = {
            "radial_depth": False,
            "scale_to_meters": 1.0,
            "range": [0, 100],
            "dimensions": {"height": 4, "width": 8},
        }
        if values is None:
            values = np.arange(32, dtype=np.float32).reshape(4, 8) + 1
    elif values is None:
        values = np.arange(96, dtype=np.float32).reshape(4, 8, 3) / 255
    head["modality"]["meta"]["dimensions"].update(
        height=values.shape[0], width=values.shape[1]
    )
    head["modality"]["meta"]["file_types"] = ["npy"]
    head["addons"]["euler_loading"] = {
        "version": "1.0",
        "loader": "generic_dense_depth",
        "function": modality,
    }
    writer = DatasetWriter(root, head=copy.deepcopy(head), metadata_scope=scope)
    path = writer.get_path(
        "/scene:scene_01/camera:camera_0/frame_001",
        "frame_001.npy",
        attributes={"source_tag": "synthetic"},
    )
    np.save(path, values)
    writer.save_index()
    dataset = MultiModalDataset(
        modalities={
            modality: Modality(
                str(root),
                metadata_scope=scope,
                modality_type=modality,
                loader=getattr(generic_dense_depth, modality),
                writer=getattr(generic_dense_depth, "write_" + modality),
            )
        },
        transforms=transforms,
    )
    return dataset, head, values


def reload_dataset(root, *, modality="rgb", scope=None):
    from euler_loading import Modality, MultiModalDataset
    from euler_loading.loaders.cpu import generic_dense_depth

    return MultiModalDataset(
        modalities={
            modality: Modality(
                str(root),
                metadata_scope=scope,
                modality_type=modality,
                loader=getattr(generic_dense_depth, modality),
            )
        }
    )


def file_entries(index):
    def visit(node):
        yield from node.get("files", [])
        for child in node.get("children", {}).values():
            yield from visit(child)

    return list(visit(index["index"]))
