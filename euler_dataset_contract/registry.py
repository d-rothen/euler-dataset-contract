"""Registry of shared dataset-contract definitions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable


Validator = Callable[[Any], str | None]
_MISSING = object()

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

    @property
    def has_default(self) -> bool:
        return self.default is not _MISSING


def _validate_rgb_array(value: Any) -> str | None:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or not all(isinstance(v, int) and 0 <= v <= 255 for v in value)
    ):
        return "an array of 3 integers (0-255)"
    return None


def _validate_numeric_range(value: Any) -> str | None:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(v, (int, float)) for v in value)
    ):
        return "an array of 2 numbers [min, max]"
    if value[0] > value[1]:
        return "an array of 2 numbers [min, max] where min <= max"
    return None


def _validate_positive_int(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return "a positive integer"
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
}

_SEMANTIC_SEGMENTATION_FIELDS: dict[str, MetaFieldDefinition] = {
    "skyclass": MetaFieldDefinition(
        accepted_type=list,
        type_label="an array of 3 integers (0-255)",
        description=(
            "RGB colour value identifying the sky class in the segmentation map."
        ),
        validator=_validate_rgb_array,
        default=[0, 0, 0],
        json_schema={
            "type": "array",
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
    if modality_key in _MODALITY_META_FIELD_DEFINITIONS and not overwrite:
        raise ValueError(
            f"Modality {modality_key!r} is already registered; "
            "pass overwrite=True to replace it"
        )
    _MODALITY_META_FIELD_DEFINITIONS[modality_key] = deepcopy(fields)


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
