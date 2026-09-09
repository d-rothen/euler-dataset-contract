"""Generate synthetic Phase 1 descriptors and canonical test vectors; no arrays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from euler_dataset_contract import (
    TransformsAddon,
    bound_derivation_digest,
    parse_dataset_head,
    recipe_digest,
)
from euler_dataset_contract.canonical import canonical_digest, canonical_json

ROOT = Path(__file__).resolve().parents[1]


def fixture() -> dict:
    fields, sources = {}, {}
    kinds = {
        "rgb": "image",
        "depth": "depth",
        "valid_mask": "mask",
        "intrinsics": "intrinsics",
        "ray_map": "ray_map",
    }
    for name, kind in kinds.items():
        matrix = kind == "intrinsics"
        vector = kind in {"image", "ray_map"}
        profile = {
            "kind": kind,
            "layout": "matrix" if matrix else "HWC" if vector else "HW",
            "shape": [3, 3] if matrix else [480, 960, 3] if vector else [480, 960],
            "dtype": "bool" if kind == "mask" else "float32",
            "image_plane": "camera_0",
            "unit": "meter"
            if kind == "depth"
            else "pixel"
            if matrix
            else "dimensionless",
            "invalid": {
                "non_finite": False,
                "sentinel": 0 if kind == "depth" else None,
            },
        }
        if kind in {"depth", "ray_map", "intrinsics"}:
            profile["frame"] = "camera_0_optical"
        if kind == "depth":
            profile["depth_kind"] = "planar_z"
        if kind == "ray_map":
            profile.update(normalization="homogeneous", components=["x", "y", "z"])
        if kind == "mask":
            profile["meaning"] = "true denotes valid source depth"
        if matrix:
            profile["camera_model"] = "pinhole"
        revision = canonical_digest({"synthetic_revision": name})
        binding = {
            "source": "source_" + name,
            "profile": profile,
            "policy": {
                "interpolation": "nearest" if kind == "mask" else "bilinear",
                "rays": "resample_normalize" if kind == "ray_map" else "preserve",
            },
        }
        if matrix:
            binding["selection"] = "camera_0"
            binding["calibration"] = {
                "full_id": "/scene_01/camera_0/calibration",
                "revision": revision,
                "image_plane": "camera_0",
                "frame": "camera_0_optical",
                "camera_model": "pinhole",
                "applies_to": ["rgb", "depth", "valid_mask", "ray_map"],
            }
        fields[name] = binding
        sources[binding["source"]] = {
            "dataset_id": "synthetic_" + name,
            "modality_key": "spherical_map" if kind == "ray_map" else name,
            "metadata_scope": name,
            "revision": revision,
            "head_digest": canonical_digest({"synthetic_head": name}),
            "index_digest": canonical_digest({"synthetic_index": name}),
            "verification": "metadata",
            "decoder": {
                "id": "synthetic.affine_fixture",
                "version": "1.0",
                "profile_digest": canonical_digest(profile),
            },
        }
    recipe = {
        "version": "1.0",
        "required_features": [
            "spatial.resize_crop",
            "bindings.qualified",
            "profiles.decoded",
        ],
        "reference_field": "rgb",
        "fields": fields,
        "image_planes": {
            "camera_0": {
                "size": [480, 960],
                "frame": "camera_0_optical",
                "camera_model": "pinhole",
            }
        },
        "execution": {
            "backend": "torch_cpu",
            "versions": {"numpy": "2.4.6", "torch": "2.12.1+cu130"},
            "nearest": "floor",
            "antialias": False,
            "integer_rounding": "ties_to_even",
            "vector_epsilon": 1e-12,
            "numeric_tolerance": {"atol": 1e-5, "rtol": 1e-5},
        },
        "operations": [
            {
                "id": "resize_1",
                "op": "euler_loading.resize",
                "version": "1.0",
                "parameters": {"size": [384, 768]},
            },
            {
                "id": "crop_2",
                "op": "euler_loading.crop",
                "version": "1.0",
                "parameters": {"size": [320, 640]},
            },
        ],
    }
    addon = TransformsAddon(
        {
            "version": "1.0",
            "state": "planned",
            "sources": sources,
            "recipe": recipe,
            "recipe_digest": recipe_digest(recipe),
        }
    ).to_dict()
    full_ids = {name: "/scene_01/camera_0/frame_001" for name in sources}
    full_ids["source_intrinsics"] = "/scene_01/camera_0/calibration"
    return {
        "name": "five-field",
        "description": "Synthetic metadata-only declarations for the Phase 0 documented-five-field values; no content verification or execution receipt.",
        "addon": addon,
        "representation": {
            "version": "1.0",
            "modality_id": "geometry.camera.depth",
            "decoded": fields["depth"]["profile"],
        },
        "source_full_ids": full_ids,
        "bound_derivation_digest": bound_derivation_digest(addon, full_ids),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    values = [
        None,
        {},
        {"b": 1.0, "a": -0.0},
        [1, 2, 3],
        0.1,
        {"unicode": "é/雪", "control": "\n\t\u0001"},
        {"e\u0301": 1, "é": 2},
    ]
    data = fixture()
    head = {
        "contract": {"kind": "dataset_head", "version": "1.0"},
        "dataset": {
            "id": "synthetic_rgb",
            "name": "Synthetic planned five-field input",
        },
        "modality": {
            "key": "rgb",
            "meta": {
                "range": [0, 1],
                "dimensions": {"height": 480, "width": 960, "channels": 3},
            },
        },
        "addons": {
            "euler_representation": {
                "version": "1.0",
                "modality_id": "appearance.camera.color",
                "decoded": data["addon"]["recipe"]["fields"]["rgb"]["profile"],
            },
            "euler_transforms": data["addon"],
        },
    }
    files = {
        "descriptors/five-field.json": data,
        "descriptors/canonical-vectors.json": {
            "encoding": "euler-json-1",
            "vectors": [
                {
                    "value": value,
                    "canonical": canonical_json(value),
                    "digest": canonical_digest(value),
                }
                for value in values
            ],
        },
        "heads/valid/phase1-planned-five-field.json": head,
        "heads/canonical/phase1-planned-five-field.json": parse_dataset_head(
            head
        ).to_mapping(),
    }
    for filename, value in files.items():
        path = ROOT / "fixtures" / filename
        rendered = (
            json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        )
        if args.check:
            if path.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"Stale Phase 1 fixture: {filename}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
