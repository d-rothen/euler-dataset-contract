"""JSON Schema builders for dataset contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .registry import (
    DATASET_CONTRACT_VERSION,
    DATASET_HEAD_KIND,
    SHARED_META_FIELD_DEFINITIONS,
    iter_modality_meta_fields,
)

_TYPE_MAP: dict[type, str] = {
    bool: "boolean",
    int: "number",
    float: "number",
    str: "string",
    list: "array",
    dict: "object",
}


def _json_schema_type(accepted: type | tuple[type, ...]) -> dict[str, Any]:
    if isinstance(accepted, tuple):
        types = sorted({_TYPE_MAP[t] for t in accepted})
    else:
        types = [_TYPE_MAP[accepted]]

    if len(types) == 1:
        return {"type": types[0]}
    return {"type": types}


def build_meta_schema() -> dict[str, Any]:
    modality_schemas: dict[str, dict[str, Any]] = {}

    for modality_key, fields in sorted(iter_modality_meta_fields().items()):
        properties: dict[str, Any] = {}
        for name, definition in SHARED_META_FIELD_DEFINITIONS.items():
            type_clause = deepcopy(
                definition.json_schema
                if definition.json_schema is not None
                else _json_schema_type(definition.accepted_type)
            )
            properties[name] = {
                **type_clause,
                "description": definition.description,
            }

        required: list[str] = []
        for field_name, definition in sorted(fields.items()):
            type_clause = deepcopy(
                definition.json_schema
                if definition.json_schema is not None
                else _json_schema_type(definition.accepted_type)
            )
            prop = {
                **type_clause,
                "description": definition.description,
            }
            if definition.has_default:
                prop["default"] = deepcopy(definition.default)
            properties[field_name] = prop
            required.append(field_name)

        modality_schemas[modality_key] = {
            "type": "object",
            "description": (
                f"Required meta fields when modality.key is {modality_key!r}."
            ),
            "properties": properties,
            "required": required,
            "additionalProperties": True,
        }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Euler dataset modality meta schemas",
        "description": (
            "Defines shared and modality-specific meta fields for "
            "each modality.key value."
        ),
        "type": "object",
        "properties": modality_schemas,
    }


def build_dataset_head_schema() -> dict[str, Any]:
    meta_schema = build_meta_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Euler dataset head schema",
        "description": "Common cross-package dataset head contract.",
        "type": "object",
        "required": ["contract", "dataset", "modality"],
        "properties": {
            "contract": {
                "type": "object",
                "required": ["kind", "version"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "const": DATASET_HEAD_KIND,
                    },
                    "version": {
                        "type": "string",
                        "default": DATASET_CONTRACT_VERSION,
                    },
                },
                "additionalProperties": False,
            },
            "dataset": {
                "type": "object",
                "required": ["id", "name"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "attributes": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            "modality": {
                "type": "object",
                "required": ["key"],
                "properties": {
                    "key": {"type": "string"},
                    "meta": meta_schema,
                },
                "additionalProperties": False,
            },
            "addons": {
                "type": "object",
                "propertyNames": {
                    "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
                },
                "additionalProperties": {
                    "type": "object",
                    "required": ["version"],
                    "properties": {
                        "version": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
        },
        "additionalProperties": False,
    }
