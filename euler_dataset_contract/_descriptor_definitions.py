"""The shared schema definitions and a private validator for their small subset.

This is deliberately not a general JSON Schema implementation. Every keyword
used here is checked below; cross-reference checks live in descriptors.py.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .canonical import canonical_json


def obj(properties: dict, required: tuple = (), **extra: Any) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
        **extra,
    }


def enum(*values: Any, **extra: Any) -> dict:
    return {"enum": list(values), **extra}


def array(items: dict, minimum: int = 0, **extra: Any) -> dict:
    return {"type": "array", "items": items, "minItems": minimum, **extra}


def mapping(items: dict) -> dict:
    return {
        "type": "object",
        "propertyNames": TOKEN,
        "additionalProperties": items,
        "minProperties": 1,
    }


TEXT = {"type": "string", "minLength": 1}
TOKEN = {**TEXT, "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"}
ID = {**TEXT, "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*){2,}$"}
DIGEST = {**TEXT, "pattern": "^sha256:[0-9a-f]{64}$"}
FULL_ID = {
    **TEXT,
    "pattern": r"^/(?!\.{1,2}(?:/|$))[^/]+(?:/(?!\.{1,2}(?:/|$))[^/]+)*$",
}
INTEGER = {"type": "integer", "minimum": 1}
NUMBER = {"type": "number"}
SIZE = array(INTEGER, 2, maxItems=2)
OFFSET = array({"type": "integer", "minimum": 0}, 2, maxItems=2)
FEATURES = array(TEXT, uniqueItems=True, default=[])
DIAGNOSTICS = array(TEXT)
INVALID = obj(
    {"non_finite": {"type": "boolean"}, "sentinel": {"type": ["number", "null"]}},
    ("non_finite", "sentinel"),
)
SHAPE = array({"oneOf": [INTEGER, TOKEN]}, 2, maxItems=4)

PROFILE_PROPERTIES = {
    "kind": enum(
        "image",
        "depth",
        "mask",
        "ray_map",
        "intrinsics",
        "point_map",
        "point_cloud",
        "extrinsics",
        "generic",
    ),
    "layout": enum("HW", "CHW", "HWC", "NHW", "NCHW", "NHWC", "matrix", "NC"),
    "shape": SHAPE,
    "dtype": enum(
        "bool", "uint8", "uint16", "int16", "int32", "int64", "float32", "float64"
    ),
    "unit": TEXT,
    "invalid": INVALID,
    "image_plane": TOKEN,
    "frame": TEXT,
    "depth_kind": enum("planar_z", "radial"),
    "normalization": enum("homogeneous", "unit", "none", "unit_or_zero"),
    "components": array(TEXT, 3, uniqueItems=True),
    "camera_model": enum("pinhole", "fisheye", "other"),
    "meaning": TEXT,
    "source_frame": TEXT,
    "target_frame": TEXT,
    "direction": enum("target_from_source", "source_from_target"),
}
PROFILE = obj(
    PROFILE_PROPERTIES,
    ("kind", "layout", "shape", "dtype", "unit", "invalid"),
    allOf=[
        {
            "if": {
                "properties": {
                    "kind": enum(
                        "image", "depth", "mask", "ray_map", "point_map", "intrinsics"
                    )
                }
            },
            "then": {"required": ["image_plane"]},
        },
        {
            "if": {"properties": {"kind": enum("depth")}},
            "then": {"required": ["depth_kind", "frame"]},
        },
        {
            "if": {"properties": {"kind": enum("ray_map", "point_map", "point_cloud")}},
            "then": {"required": ["components", "frame"]},
        },
        {
            "if": {"properties": {"kind": enum("ray_map")}},
            "then": {"required": ["normalization"]},
        },
        {
            "if": {"properties": {"kind": enum("mask")}},
            "then": {"required": ["meaning"]},
        },
        {
            "if": {"properties": {"kind": enum("intrinsics")}},
            "then": {
                "required": ["camera_model", "frame"],
                "properties": {
                    "layout": enum("matrix"),
                    "shape": {"const": [3, 3]},
                    "dtype": enum("float32", "float64"),
                    "unit": enum("pixel"),
                },
            },
        },
        {
            "if": {"properties": {"kind": enum("extrinsics")}},
            "then": {
                "required": ["source_frame", "target_frame", "direction"],
                "properties": {"layout": enum("matrix"), "shape": {"const": [4, 4]}},
            },
        },
        {
            "if": {"properties": {"kind": enum("point_cloud")}},
            "then": {"properties": {"layout": enum("NC")}},
        },
        {
            "if": {
                "properties": {
                    "kind": enum("image", "depth", "mask", "ray_map", "point_map")
                }
            },
            "then": {
                "properties": {
                    "layout": enum("HW", "CHW", "HWC", "NHW", "NCHW", "NHWC")
                }
            },
        },
        *[
            {
                "if": {"properties": {"layout": enum(layout)}},
                "then": {"properties": {"shape": {"minItems": rank, "maxItems": rank}}},
            }
            for layout, rank in (
                ("HW", 2),
                ("CHW", 3),
                ("HWC", 3),
                ("NHW", 3),
                ("NCHW", 4),
                ("NHWC", 4),
                ("matrix", 2),
                ("NC", 2),
            )
        ],
    ],
)
PLANE = obj(
    {"size": SIZE, "frame": TEXT, "camera_model": enum("pinhole", "fisheye", "other")},
    ("size", "frame", "camera_model"),
)
CALIBRATION = obj(
    {
        "full_id": FULL_ID,
        "revision": DIGEST,
        "image_plane": TOKEN,
        "frame": TEXT,
        "camera_model": enum("pinhole", "fisheye", "other"),
        "applies_to": array(TOKEN, 1, uniqueItems=True),
    },
    ("full_id", "revision", "image_plane", "frame", "camera_model", "applies_to"),
)
DECODER = obj(
    {"id": TEXT, "version": TEXT, "profile_digest": DIGEST},
    ("id", "version", "profile_digest"),
)
SOURCE = obj(
    {
        "dataset_id": TOKEN,
        "modality_key": TOKEN,
        "metadata_scope": TEXT,
        "revision": DIGEST,
        "head_digest": DIGEST,
        "index_digest": DIGEST,
        "decoder": DECODER,
        "verification": enum("metadata", "content", "immutable_snapshot"),
        "content_digest": DIGEST,
        "immutable_snapshot": TEXT,
        "locator": TEXT,
        "diagnostics": DIAGNOSTICS,
    },
    (
        "dataset_id",
        "modality_key",
        "metadata_scope",
        "revision",
        "head_digest",
        "index_digest",
        "decoder",
        "verification",
    ),
    allOf=[
        {
            "if": {"properties": {"verification": enum("content")}},
            "then": {"required": ["content_digest"]},
        },
        {
            "if": {"properties": {"verification": enum("immutable_snapshot")}},
            "then": {"required": ["immutable_snapshot"]},
        },
    ],
)
POLICY = obj(
    {
        "interpolation": enum("nearest", "bilinear", default="bilinear"),
        "invalid_depth": enum("legacy_blend", "validity_aware", default="legacy_blend"),
        "rays": enum(
            "preserve", "resample_normalize", "regenerate", default="preserve"
        ),
        "mask_threshold": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "default": 0.5,
        },
    },
    (),
)
FIELD = obj(
    {
        "source": TOKEN,
        "profile": PROFILE,
        "policy": POLICY,
        "selection": TEXT,
        "calibration": CALIBRATION,
    },
    ("source", "profile", "policy"),
    allOf=[
        {
            "if": {
                "properties": {"profile": {"properties": {"kind": enum("intrinsics")}}}
            },
            "then": {"required": ["calibration"]},
        },
        {
            "if": {"properties": {"profile": {"properties": {"kind": enum("mask")}}}},
            "then": {
                "properties": {
                    "policy": {
                        "properties": {"interpolation": enum("nearest")},
                        "required": ["interpolation"],
                    }
                }
            },
        },
        {
            "if": {
                "properties": {
                    "profile": {
                        "properties": {
                            "kind": enum(
                                "image",
                                "depth",
                                "mask",
                                "intrinsics",
                                "point_map",
                                "point_cloud",
                                "extrinsics",
                                "generic",
                            )
                        }
                    }
                }
            },
            "then": {
                "properties": {"policy": {"properties": {"rays": enum("preserve")}}}
            },
        },
        {
            "if": {
                "properties": {
                    "profile": {
                        "properties": {
                            "kind": enum(
                                "image",
                                "mask",
                                "ray_map",
                                "intrinsics",
                                "point_map",
                                "point_cloud",
                                "extrinsics",
                                "generic",
                            )
                        }
                    }
                }
            },
            "then": {
                "properties": {
                    "policy": {"properties": {"invalid_depth": enum("legacy_blend")}}
                }
            },
        },
    ],
)
EXECUTION = obj(
    {
        "backend": enum("torch_cpu", "pillow_cpu"),
        "versions": {
            "type": "object",
            "additionalProperties": TEXT,
            "minProperties": 1,
        },
        "device": enum("cpu", default="cpu"),
        "work_dtype": enum("float32", default="float32"),
        "output_dtype": enum("preserve", default="preserve"),
        "boundary": enum("edge", default="edge"),
        "nearest": enum("floor", "half_pixel"),
        "antialias": {"type": "boolean"},
        "integer_rounding": enum("ties_to_even", "legacy_truncate"),
        "vector_epsilon": {"type": "number", "exclusiveMinimum": 0},
        "numeric_tolerance": obj(
            {
                "atol": {"type": "number", "minimum": 0},
                "rtol": {"type": "number", "minimum": 0},
            },
            ("atol", "rtol"),
        ),
    },
    (
        "backend",
        "versions",
        "nearest",
        "antialias",
        "integer_rounding",
        "vector_epsilon",
        "numeric_tolerance",
    ),
)
OPERATION = {
    "oneOf": [
        obj(
            {
                "id": TOKEN,
                "op": enum("euler_loading.resize"),
                "version": enum("1.0"),
                "parameters": obj(
                    {
                        "size": SIZE,
                        "pixel_centers": enum("half_pixel", default="half_pixel"),
                    },
                    ("size",),
                ),
            },
            ("id", "op", "version", "parameters"),
        ),
        obj(
            {
                "id": TOKEN,
                "op": enum("euler_loading.crop"),
                "version": enum("1.0"),
                "parameters": {
                    "oneOf": [
                        obj(
                            {
                                "size": SIZE,
                                "anchor": enum(
                                    "center",
                                    "top_left",
                                    "top_right",
                                    "bottom_left",
                                    "bottom_right",
                                    default="center",
                                ),
                            },
                            ("size",),
                        ),
                        obj({"size": SIZE, "offset": OFFSET}, ("size", "offset")),
                    ]
                },
            },
            ("id", "op", "version", "parameters"),
        ),
    ]
}
RECIPE = obj(
    {
        "version": enum("1.0"),
        "required_features": FEATURES,
        "reference_field": TOKEN,
        "image_planes": mapping(PLANE),
        "fields": mapping(FIELD),
        "execution": EXECUTION,
        "operations": array(OPERATION, 1),
        "diagnostics": DIAGNOSTICS,
    },
    ("version", "reference_field", "image_planes", "fields", "execution", "operations"),
)
TRANSFORMS = obj(
    {
        "version": enum("1.0"),
        "state": enum("planned"),
        "required_features": FEATURES,
        "sources": mapping(SOURCE),
        "recipe": RECIPE,
        "recipe_digest": DIGEST,
        "diagnostics": DIAGNOSTICS,
    },
    ("version", "state", "sources", "recipe", "recipe_digest"),
)
REPRESENTATION = obj(
    {
        "version": enum("1.0"),
        "required_features": FEATURES,
        "modality_id": ID,
        "decoded": PROFILE,
        "storage": obj({"encoding": TEXT, "profile": PROFILE}, ("encoding", "profile")),
        "diagnostics": DIAGNOSTICS,
    },
    ("version", "modality_id", "decoded"),
    allOf=[
        {
            "if": {"properties": {"modality_id": enum(identity)}},
            "then": {"properties": {"decoded": {"properties": {"kind": enum(*kinds)}}}},
        }
        for identity, kinds in {
            "appearance.camera.color": ("image",),
            "geometry.camera.depth": ("depth",),
            "geometry.camera.intrinsics": ("intrinsics",),
            "geometry.camera.extrinsics": ("extrinsics",),
            "geometry.camera.ray_direction": ("ray_map",),
            "geometry.scene.points": ("point_map", "point_cloud"),
            "signal.grid.array": ("generic",),
            "signal.grid.scalar": ("generic",),
        }.items()
    ],
)
DEFINITIONS = {
    "profile": PROFILE,
    "image_plane": PLANE,
    "calibration": CALIBRATION,
    "source": SOURCE,
    "field": FIELD,
    "execution": EXECUTION,
    "operation": OPERATION,
    "recipe": RECIPE,
    "euler_representation": REPRESENTATION,
    "euler_transforms": TRANSFORMS,
}


def _matches(value: Any, schema: dict) -> bool:
    try:
        check(value, schema, "value")
        return True
    except ValueError:
        return False


def check(value: Any, schema: dict, path: str) -> None:
    def fail(message: str) -> None:
        raise ValueError(f"{path}: {message}")

    if "oneOf" in schema:
        matches = [branch for branch in schema["oneOf"] if _matches(value, branch)]
        if len(matches) != 1:
            fail(
                "must match exactly one supported descriptor variant (operation/version/parameters)"
            )
    for branch in schema.get("allOf", []):
        check(value, branch, path)
    if "if" in schema and _matches(value, schema["if"]):
        check(value, schema["then"], path)
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    types = {
        "object": type(value) is dict,
        "array": type(value) is list,
        "string": type(value) is str,
        "number": type(value) in (int, float),
        "integer": type(value) in (int, float) and value == int(value),
        "boolean": type(value) is bool,
        "null": value is None,
        None: True,
    }
    if not any(types[item] for item in kinds):
        fail(f"expected {kind}")
    # JSON equality keeps booleans distinct from numbers.
    if "enum" in schema and canonical_json(value) not in [
        canonical_json(v) for v in schema["enum"]
    ]:
        fail(f"expected one of {schema['enum']}")
    if "const" in schema and canonical_json(value) != canonical_json(schema["const"]):
        fail(f"expected {schema['const']!r}")
    if type(value) is dict:
        for key in schema.get("required", []):
            if key not in value:
                fail(f"missing required {key}")
        if len(value) < schema.get("minProperties", 0):
            fail("object cannot be empty")
        for key, item in value.items():
            if "propertyNames" in schema:
                check(key, schema["propertyNames"], path + " key")
            child = schema.get("properties", {}).get(
                key, schema.get("additionalProperties", {})
            )
            if child is False:
                fail(f"unknown key {key}")
            check(item, child, path + "." + key)
    if type(value) is list:
        if (
            not schema.get("minItems", 0)
            <= len(value)
            <= schema.get("maxItems", float("inf"))
        ):
            fail("array length is out of bounds")
        if schema.get("uniqueItems") and len({canonical_json(v) for v in value}) != len(
            value
        ):
            fail("array items must be unique")
        for index, item in enumerate(value):
            check(item, schema.get("items", {}), f"{path}[{index}]")
    if type(value) is str:
        if len(value) < schema.get("minLength", 0):
            fail("string cannot be empty")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            fail(f"must match {schema['pattern']}")
    if type(value) in (int, float):
        for key, valid in (
            ("minimum", lambda n: value >= n),
            ("maximum", lambda n: value <= n),
            ("exclusiveMinimum", lambda n: value > n),
        ):
            if key in schema and not valid(schema[key]):
                fail(f"must satisfy {key}={schema[key]}")


def normalize(value: Any, schema: dict) -> Any:
    """Expand only versioned defaults; never reorder arrays or infer semantics."""
    if "oneOf" in schema:
        schema = next(branch for branch in schema["oneOf"] if _matches(value, branch))
    if type(value) is dict:
        result = deepcopy(value)
        for key, child in schema.get("properties", {}).items():
            if key not in result and "default" in child:
                result[key] = deepcopy(child["default"])
        return {
            key: normalize(
                item,
                schema.get("properties", {}).get(
                    key, schema.get("additionalProperties", {})
                ),
            )
            for key, item in result.items()
        }
    if type(value) is list:
        return [normalize(item, schema.get("items", {})) for item in value]
    return value
