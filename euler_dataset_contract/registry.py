"""Registry of shared dataset-contract definitions."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .source_grid import SOURCE_GRID_JSON_SCHEMA, check_source_grid

# This alias is evaluated at import time even with postponed annotations.
# Optional keeps the package importable on the declared Python 3.9 minimum.
Validator = Callable[[Any], Optional[str]]


class _Missing:
    """Marks a field without a default. Copies stay the same object, so
    ``has_default`` survives the deep copies the registry hands out."""

    def __repr__(self) -> str:
        return "<no default>"

    def __copy__(self) -> "_Missing":
        return self

    def __deepcopy__(self, memo: dict) -> "_Missing":
        return self


_MISSING = _Missing()
_TOKEN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DATASET_HEAD_KIND = "dataset_head"
DATASET_CONTRACT_VERSION = "1.0"


@dataclass(frozen=True)
class MetaFieldDefinition:
    accepted_type: type | tuple[type, ...]
    type_label: str
    description: str
    validator: Validator | None = None
    default: Any = _MISSING
    json_schema: dict[str, Any] | None = None
    #: A required field must be present in every head of its modality; an
    #: optional one is validated only when a head declares it.
    required: bool = True

    @property
    def has_default(self) -> bool:
        return self.default is not _MISSING


def _validate_rgb_array(value: Any) -> str | None:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or not all(
            not isinstance(v, bool) and isinstance(v, int) and 0 <= v <= 255
            for v in value
        )
    ):
        return "an array of 3 integers (0-255)"
    return None


def _validate_optional_rgb_array(value: Any) -> str | None:
    if value is None:
        return None
    error = _validate_rgb_array(value)
    return None if error is None else f"{error} or null"


def _validate_numeric_range(value: Any) -> str | None:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(
            not isinstance(v, bool) and isinstance(v, (int, float)) for v in value
        )
    ):
        return "an array of 2 numbers [min, max]"
    if value[0] > value[1]:
        return "an array of 2 numbers [min, max] where min <= max"
    return None


def _validate_positive_int(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return "a positive integer"
    return None


def _validate_boolean(value: Any) -> str | None:
    return None if isinstance(value, bool) else "a boolean"


def _is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and value == value
        and value not in (float("inf"), float("-inf"))
    )


def _validate_invalid(value: Any) -> str | None:
    if (
        not isinstance(value, dict)
        or set(value) != {"non_finite", "sentinel"}
        or not isinstance(value["non_finite"], bool)
    ):
        return "an object {'non_finite': boolean, 'sentinel': number or null}"
    if value["sentinel"] is not None and not _is_finite_number(value["sentinel"]):
        return (
            "an object {'non_finite': boolean, 'sentinel': number or null} "
            "with a finite sentinel"
        )
    return None


def validate_dimensions_dict(value: Any) -> str | None:
    if not isinstance(value, dict) or not value:
        return "a non-empty object"

    for axis, size in value.items():
        if not isinstance(axis, str) or not axis:
            return "keys must be non-empty strings"
        if not (
            axis[0].isalpha() or axis[0] == "_"
        ) or any(not (ch.isalnum() or ch == "_") for ch in axis):
            return "keys must contain only letters, digits, or underscores"
        err = _validate_positive_int(size)
        if err is not None:
            return f"{axis!r} must be {err}"
    return None


def _validate_file_types(value: Any) -> str | None:
    if not isinstance(value, list) or not value:
        return "a non-empty array of unique file type strings"

    normalized: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            return "a non-empty array of unique file type strings"
        token = item.strip().lower().lstrip(".")
        if not token:
            return "a non-empty array of unique file type strings"
        if "/" in token or "\\" in token or any(ch.isspace() for ch in token):
            return "a non-empty array of unique file type strings"
        normalized.add(token)

    if len(normalized) != len(value):
        return "a non-empty array of unique file type strings"
    return None


SHARED_META_FIELD_DEFINITIONS: dict[str, MetaFieldDefinition] = {
    "dimensions": MetaFieldDefinition(
        accepted_type=dict,
        type_label="a non-empty object",
        description=(
            "Dataset-wide nominal sample dimensions keyed by semantic axis "
            "names (for example {'height': 375, 'width': 1242, 'channels': 3}). "
            "Omit this field when there is no single dataset-wide shape."
        ),
        validator=validate_dimensions_dict,
        json_schema={
            "type": "object",
            "propertyNames": {
                "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
            },
            "minProperties": 1,
            "additionalProperties": {
                "type": "integer",
                "minimum": 1,
            },
            "examples": [
                {"height": 375, "width": 1242, "channels": 3},
                {"time": 16, "features": 512},
                {"x": 256, "y": 256, "z": 64},
            ],
            "x-ui": {
                "widget": "keyValueTable",
                "keyLabel": "Axis",
                "valueLabel": "Size",
                "allowCustomKeys": True,
                "suggestedKeys": [
                    "height",
                    "width",
                    "channels",
                    "depth",
                    "time",
                    "features",
                ],
            },
        },
    ),
    "file_types": MetaFieldDefinition(
        accepted_type=list,
        type_label="a non-empty array of unique file type strings",
        description=(
            "Observed data file types for this modality, stored as lowercase "
            "extensions without leading dots (for example ['jpg', 'png'])."
        ),
        validator=_validate_file_types,
        json_schema={
            "type": "array",
            "items": {"type": "string", "pattern": "^[^./\\\\\\s][^/\\\\\\s]*$"},
            "minItems": 1,
            "uniqueItems": True,
            "examples": [["png"], ["jpg", "png"], ["npy"]],
        },
    ),
    "invalid": MetaFieldDefinition(
        accepted_type=dict,
        type_label="an object {'non_finite': boolean, 'sentinel': number or null}",
        description=(
            "How pixels without a valid value are marked in the values the "
            "loader returns: 'sentinel' is the finite value that marks them "
            "(null: none), and 'non_finite' whether NaN or infinite values can "
            "appear, which then mark invalid pixels too. The same shape and "
            "meaning as a representation profile's 'invalid'. Omitted: not "
            "declared, so consumers apply their own rule (for depth, a value "
            "that is non-finite or not positive is invalid)."
        ),
        validator=_validate_invalid,
        json_schema={
            "type": "object",
            "properties": {
                "non_finite": {
                    "type": "boolean",
                    "description": "Whether NaN or infinite values can appear; they mark invalid pixels.",
                },
                "sentinel": {
                    "type": ["number", "null"],
                    "description": "The finite value that marks invalid pixels, or null for none.",
                },
            },
            "required": ["non_finite", "sentinel"],
            "additionalProperties": False,
            "examples": [
                {"non_finite": False, "sentinel": 0},
                {"non_finite": True, "sentinel": None},
            ],
        },
    ),
    "sparse": MetaFieldDefinition(
        accepted_type=bool,
        type_label="a boolean",
        description=(
            "Whether the raster holds measurements at only some of its pixels, "
            "the rest invalid as 'invalid' declares (without it, consumers "
            "take 0 for depth), as in lidar-derived depth or disparity. "
            "Consumers must not interpolate between samples: a resize moves each "
            "measurement to its nearest target pixel, keeping the nearest "
            "surface, and evaluation scores the measured pixels. Default false."
        ),
        validator=_validate_boolean,
        json_schema={"type": "boolean", "default": False},
    ),
    "source_grid": MetaFieldDefinition(
        accepted_type=dict,
        type_label="an object with 'size' and 'affine'",
        description=(
            "How this dataset's pixel grid derives from the grid of the images "
            "it was computed from, such as a prediction from its model input: "
            "the source [height, width] and the affine [[sx, 0, tx], [0, sy, ty]] "
            "mapping source pixel centres to this grid (K_out = T @ K_in). A "
            "file's attributes.source_grid overrides it for that sample."
        ),
        validator=check_source_grid,
        json_schema=SOURCE_GRID_JSON_SCHEMA,
    ),
}

def _validate_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return "a non-empty string"
    return None


def _validate_token(value: Any) -> str | None:
    if not isinstance(value, str) or not _TOKEN_PATTERN.fullmatch(value):
        return "a token (letters, digits, underscores; not starting with a digit)"
    return None


def _choice(*choices: str) -> Validator:
    label = "one of " + ", ".join(repr(choice) for choice in choices)

    def validate(value: Any) -> str | None:
        return None if value in choices else label

    return validate


def _validate_columns(value: Any) -> str | None:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
        or len(set(value)) != len(value)
    ):
        return "a non-empty array of unique non-empty strings"
    return None


def _text_field(description: str, examples: list[str]) -> MetaFieldDefinition:
    return MetaFieldDefinition(
        accepted_type=str,
        type_label="a non-empty string",
        description=description,
        validator=_validate_text,
        json_schema={"type": "string", "minLength": 1, "pattern": r"\S", "examples": examples},
        required=False,
    )


def _choice_field(description: str, *choices: str) -> MetaFieldDefinition:
    return MetaFieldDefinition(
        accepted_type=str,
        type_label="one of " + ", ".join(repr(choice) for choice in choices),
        description=description,
        validator=_choice(*choices),
        json_schema={"type": "string", "enum": list(choices)},
        required=False,
    )


# Geometry fields are optional: heads written before the contract defined them
# stay valid, while a head that declares one must use the shared vocabulary.
# The values match the euler_representation profiles (camera_model, direction)
# and the phase-0 reference heads under fixtures/heads.
_TRANSFORM_FIELDS: dict[str, MetaFieldDefinition] = {
    "source_frame": _text_field(
        "Frame the transform maps points from, e.g. a sensor name such as "
        "'LIDAR_TOP' or 'HDL_64E'.",
        ["LIDAR_TOP", "camera_0", "lidar"],
    ),
    "target_frame": _text_field(
        "Frame the transform maps points into, e.g. 'camera_optical' or 'world'.",
        ["camera_optical", "world", "CS_FRONT"],
    ),
    "direction": _choice_field(
        "How the stored 4x4 matrix relates the two frames: 'target_from_source' "
        "maps points from source_frame into target_frame (p_target = T @ "
        "p_source); 'source_from_target' is its inverse.",
        "target_from_source",
        "source_from_target",
    ),
}

_INTRINSICS_FIELDS: dict[str, MetaFieldDefinition] = {
    "camera_model": _choice_field(
        "Projection model of the camera matrix. 'pinhole' is an ideal "
        "pinhole without distortion coefficients.",
        "pinhole",
        "fisheye",
        "other",
    ),
    "image_plane": MetaFieldDefinition(
        accepted_type=str,
        type_label="a token",
        description=(
            "Identifier of the image grid the matrix describes, shared with the "
            "image modalities it applies to (e.g. 'camera_0')."
        ),
        validator=_validate_token,
        json_schema={"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        required=False,
    ),
}

_POINT_FIELDS: dict[str, MetaFieldDefinition] = {
    "representation": _choice_field(
        "Layout of the points: 'point_cloud' is an unordered (N, C) list, "
        "'point_map' one point per pixel.",
        "point_cloud",
        "point_map",
    ),
    "columns": MetaFieldDefinition(
        accepted_type=list,
        type_label="a non-empty array of unique non-empty strings",
        description=(
            "Names of a point cloud's columns in order, starting with the "
            "coordinates (e.g. ['x', 'y', 'z', 'intensity', 'ring'])."
        ),
        validator=_validate_columns,
        json_schema={
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
            "uniqueItems": True,
        },
        required=False,
    ),
    "coordinate_unit": _text_field(
        "Unit of the point coordinates, e.g. 'meters'.", ["meters"]
    ),
    "frame": _text_field(
        "Coordinate frame the points are expressed in, e.g. 'LIDAR_TOP'.",
        ["LIDAR_TOP", "lidar", "camera_0_optical"],
    ),
    "axes": _text_field(
        "Axis convention of the frame, e.g. 'x forward, y left, z up'.",
        ["x forward, y left, z up", "x right, y forward, z up"],
    ),
}


_SEMANTIC_SEGMENTATION_FIELDS: dict[str, MetaFieldDefinition] = {
    "skyclass": MetaFieldDefinition(
        accepted_type=(list, type(None)),
        type_label="an array of 3 integers (0-255) or null",
        description=(
            "Sky label of the segmentation map as an RGB triple: the value of a "
            "sky pixel when the stored file is viewed as RGB. A colour-coded map "
            "uses the sky colour (e.g. [90, 200, 255]); a single-channel class map "
            "uses [v, v, v] for sky label v (e.g. [23, 23, 23] for Cityscapes "
            "label IDs, [10, 10, 10] for train IDs); a class ID stored in one "
            "channel of a colour file keeps the other channels' values (e.g. "
            "[29, 0, 0] for an ID in the red channel). null, the default, leaves "
            "the sky undeclared: a loader then uses its own default for the "
            "dataset, or rejects the head if it has none."
        ),
        validator=_validate_optional_rgb_array,
        # Not [0, 0, 0]: producers merge this default into heads that set no
        # sky, and a triple would read as a declared sky of label 0 or black.
        default=None,
        json_schema={
            "type": ["array", "null"],
            "items": {"type": "integer", "minimum": 0, "maximum": 255},
            "minItems": 3,
            "maxItems": 3,
        },
    ),
}

_DEFAULT_MODALITY_META_FIELD_DEFINITIONS: dict[str, dict[str, MetaFieldDefinition]] = {
    "depth": {
        "radial_depth": MetaFieldDefinition(
            accepted_type=bool,
            type_label="a bool",
            description=(
                "Whether the depth values represent radial (euclidean) distance "
                "from the camera rather than perpendicular (z-buffer) depth."
            ),
            default=False,
        ),
        "scale_to_meters": MetaFieldDefinition(
            accepted_type=(int, float),
            type_label="a number",
            description=(
                "Factor that converts raw depth values to meters "
                "(e.g. 0.001 when stored in millimetres)."
            ),
            default=1.0,
        ),
        "range": MetaFieldDefinition(
            accepted_type=list,
            type_label="an array of 2 numbers [min, max]",
            description=(
                "Value range of the depth values in meters "
                "(e.g. [0, 65535] for VKITTI2)."
            ),
            validator=_validate_numeric_range,
            default=[0, 65535],
            json_schema={
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            },
        ),
    },
    "rgb": {
        "range": MetaFieldDefinition(
            accepted_type=list,
            type_label="an array of 2 numbers [min, max]",
            description=(
                "Value range of the colour channels (e.g. [0, 255] for 8-bit "
                "or [0, 1] for normalised data)."
            ),
            validator=_validate_numeric_range,
            default=[0, 255],
            json_schema={
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            },
        ),
    },
    "segmentation": deepcopy(_SEMANTIC_SEGMENTATION_FIELDS),
    "semantic_segmentation": deepcopy(_SEMANTIC_SEGMENTATION_FIELDS),
    # Every key that names one of these concepts in the modality inventory.
    "intrinsics": deepcopy(_INTRINSICS_FIELDS),
    "camera_extrinsics": deepcopy(_TRANSFORM_FIELDS),
    "extrinsics": deepcopy(_TRANSFORM_FIELDS),
    "lidar_to_gnss": deepcopy(_TRANSFORM_FIELDS),
    "lidar_pose": deepcopy(_TRANSFORM_FIELDS),
    "points_3d": deepcopy(_POINT_FIELDS),
    "point_cloud": deepcopy(_POINT_FIELDS),
    "lidar_point_cloud": deepcopy(_POINT_FIELDS),
    "sparse_depth": deepcopy(_POINT_FIELDS),
}
_MODALITY_META_FIELD_DEFINITIONS = deepcopy(_DEFAULT_MODALITY_META_FIELD_DEFINITIONS)


def iter_modality_meta_fields() -> dict[str, dict[str, MetaFieldDefinition]]:
    return deepcopy(_MODALITY_META_FIELD_DEFINITIONS)


def get_modality_meta_fields(
    modality_key: str,
) -> dict[str, MetaFieldDefinition] | None:
    fields = _MODALITY_META_FIELD_DEFINITIONS.get(modality_key)
    if fields is None:
        return None
    return deepcopy(fields)


def register_modality_meta_fields(
    modality_key: str,
    fields: dict[str, MetaFieldDefinition],
    *,
    overwrite: bool = False,
) -> None:
    if not isinstance(modality_key, str) or not _TOKEN_PATTERN.fullmatch(modality_key):
        raise ValueError(
            "modality_key must contain only letters, digits, or underscores "
            "and may not start with a digit"
        )
    if not isinstance(fields, dict):
        raise TypeError("fields must be a dict of MetaFieldDefinition values")
    for field_name, definition in fields.items():
        if not isinstance(field_name, str) or not _TOKEN_PATTERN.fullmatch(field_name):
            raise ValueError(
                "meta field names must contain only letters, digits, or "
                "underscores and may not start with a digit"
            )
        if not isinstance(definition, MetaFieldDefinition):
            raise TypeError(
                f"fields[{field_name!r}] must be a MetaFieldDefinition"
            )
    if modality_key in _MODALITY_META_FIELD_DEFINITIONS and not overwrite:
        raise ValueError(
            f"Modality {modality_key!r} is already registered; "
            "pass overwrite=True to replace it"
        )
    _MODALITY_META_FIELD_DEFINITIONS[modality_key] = deepcopy(fields)
    _refresh_legacy_modality_meta_schemas()


def build_default_meta(modality_key: str) -> dict[str, Any] | None:
    fields = _MODALITY_META_FIELD_DEFINITIONS.get(modality_key)
    if fields is None:
        return None

    defaults: dict[str, Any] = {}
    for name, definition in fields.items():
        if definition.has_default:
            defaults[name] = deepcopy(definition.default)
    return defaults


def legacy_modality_meta_schemas() -> dict[str, dict[str, tuple]]:
    result: dict[str, dict[str, tuple]] = {}
    for modality_key, fields in _MODALITY_META_FIELD_DEFINITIONS.items():
        result[modality_key] = {}
        for name, definition in fields.items():
            # The legacy view lists the fields a head must carry.
            if not definition.required:
                continue
            entry: tuple[Any, ...]
            if definition.has_default:
                entry = (
                    definition.accepted_type,
                    definition.type_label,
                    definition.description,
                    definition.validator,
                    deepcopy(definition.default),
                )
            else:
                entry = (
                    definition.accepted_type,
                    definition.type_label,
                    definition.description,
                    definition.validator,
                )
            result[modality_key][name] = entry
    return result


MODALITY_META_SCHEMAS = legacy_modality_meta_schemas()


def _refresh_legacy_modality_meta_schemas() -> None:
    """Keep the exported compatibility mapping in sync with registrations."""

    MODALITY_META_SCHEMAS.clear()
    MODALITY_META_SCHEMAS.update(legacy_modality_meta_schemas())
