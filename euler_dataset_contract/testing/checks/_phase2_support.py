"""Real five-field Phase 2 source corpus, imported only by opt-in consumers."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path


def make_source(root, *, tiny=False, count=2):
    from ds_crawler import DatasetWriter
    from euler_loading import (
        Modality,
        MultiModalDataset,
        SamplePreprocessor,
        execution_profile,
        output_encoding,
    )
    from euler_loading.output_encoding import encode_output
    from euler_loading.receipts import _digest_bytes, array_digest

    from euler_dataset_contract.testing import descriptor_fixture

    from ._support import evidence, make_sample

    data = evidence("tiny-five-field" if tiny else "documented-five-field")
    sample = make_sample(data)
    fixture = descriptor_fixture("five-field")["addon"]
    fields = deepcopy(fixture["recipe"]["fields"])
    plane = deepcopy(fixture["recipe"]["image_planes"])
    plane["camera_0"]["size"] = data["source_size"]
    root = Path(root)
    mods, hierarchy = {}, {}
    for field, binding in fields.items():
        value = sample[field]
        if isinstance(value, dict):
            value = next(iter(value.values()))
            binding["selection"] = "calibration"
            binding["calibration"]["revision"] = "sha256:" + "a" * 64
        binding["profile"]["shape"] = list(value.shape)
        binding["profile"]["dtype"] = value.dtype.name
        meta = {"file_types": ["npy"]}
        if field == "rgb":
            meta["range"] = [0, 1]
        if field == "depth":
            meta.update(scale_to_meters=1, radial_depth=False, range=[0, 100])
        head = {
            "contract": {"kind": "dataset_head", "version": "1.0"},
            "dataset": {"id": "source_" + field, "name": "Source " + field},
            "modality": {"key": field, "meta": meta},
            "addons": {
                "euler_loading": {
                    "version": "1.0",
                    "loader": "materialized",
                    "function": "data",
                }
            },
        }
        raw, decoded, profiles = encode_output(
            value, output_encoding(), binding["profile"]
        )
        attrs = {
            "note": "preserved",
            "output_encoding": {
                "encoding": output_encoding().to_dict(),
                "decoded": profiles["decoded"],
                "artifact_digest": _digest_bytes(raw),
                "decoded_digest": array_digest(decoded),
            },
        }
        writer = DatasetWriter(root / field, head=head, separator=None)
        for i in range(1 if field == "intrinsics" else count):
            fid = (
                "/scene_01/camera_0/calibration"
                if field == "intrinsics"
                else f"/scene_01/camera_0/frame_{i}"
            )
            path = writer.get_path(fid, f"{i}.npy", attributes=attrs)
            path.write_bytes(raw)
        writer.save_index()
        (hierarchy if field == "intrinsics" else mods)[field] = Modality(
            str(root / field)
        )
    dataset = MultiModalDataset(mods, hierarchical_modalities=hierarchy)
    sources = dataset.describe_transform_sources(
        fields, revisions={b["source"]: "sha256:" + "a" * 64 for b in fields.values()}
    )
    preprocessor = SamplePreprocessor.from_config(data["config"])
    descriptor = preprocessor.export_descriptor(
        sources=sources,
        fields=fields,
        image_planes=plane,
        execution=execution_profile("torch_cpu"),
    )
    return dataset, descriptor, data, sample
