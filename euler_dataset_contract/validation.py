"""Validation and normalization helpers for dataset contracts."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Callable

from .registry import (
    DATASET_CONTRACT_VERSION,
    DATASET_HEAD_KIND,
    SHARED_META_FIELD_DEFINITIONS,
    get_modality_meta_fields,
)


AddonValidator = Callable[[Any, str], None]

_CONTRACT_VERSION_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
_TOKEN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SLOT_PATTERN = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+){1,}$")
_REGISTERED_ADDON_VALIDATORS: dict[str, AddonValidator] = {}


def validate_contract_version(
    value: Any,
    context: str = "contract.version",
) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    if not _CONTRACT_VERSION_PATTERN.match(value):
        raise ValueError(
            f"{context} must look like 'major.minor' or 'major.minor.patch'"
        )


def validate_token(value: Any, context: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    if not _TOKEN_PATTERN.match(value):
        raise ValueError(
            f"{context} must contain only letters, digits, or underscores "
            "and may not start with a digit"
        )


def validate_slot(value: Any, context: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    if not _SLOT_PATTERN.match(value):
        raise ValueError(
            f"{context} must match 'segment.segment' or deeper "
            "(alphanumeric/underscore only)"
        )


def validate_dimensions_dict(value: Any, context: str) -> None:
    definition = SHARED_META_FIELD_DEFINITIONS["dimensions"]
    err = definition.validator(value) if definition.validator is not None else None
    if err is None:
        return
    if err == "a non-empty object":
        raise ValueError(f"{context} must be a non-empty object")
    if err == "keys must be non-empty strings":
        raise ValueError(f"{context} keys must be non-empty strings")
    if err == "keys must contain only letters, digits, or underscores":
        raise ValueError(
            f"{context} keys must contain only letters, digits, or underscores"
        )
    axis, _, detail = err.partition(" must be ")
    if detail:
        raise ValueError(f"{context}[{axis}] must be {detail}")
    raise ValueError(f"{context} must be {err}")


def validate_string_list(
    value: Any,
    context: str,
    *,
    allow_wildcard: bool = False,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a list of strings")
    if not value and not allow_empty:
        raise ValueError(f"{context} cannot be empty")

    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{context}[{index}] must be a non-empty string")
        if item != "*" or not allow_wildcard:
            validate_token(item, f"{context}[{index}]")
        result.append(item)
    return result


def _normalize_file_types(value: Any, context: str) -> list[str]:
    definition = SHARED_META_FIELD_DEFINITIONS["file_types"]
    if not isinstance(value, list):
        raise ValueError(
            f"{context} must be a non-empty array of unique file type strings"
        )

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                f"{context} must be a non-empty array of unique file type strings"
            )
        token = item.strip().lower().lstrip(".")
        if (
            not token
            or "/" in token
            or "\\" in token
            or any(ch.isspace() for ch in token)
        ):
            raise ValueError(
                f"{context} must be a non-empty array of unique file type strings"
            )
        normalized.append(token)

    if len(set(normalized)) != len(normalized) or not normalized:
        raise ValueError(
            f"{context} must be a non-empty array of unique file type strings"
        )

    err = definition.validator(normalized) if definition.validator is not None else None
    if err is not None:
        raise ValueError(f"{context} must be {err}")
    return sorted(normalized)


def validate_meta_dict(value: Any, modality_key: str, context: str) -> None:
    normalize_meta_dict(value, modality_key, context)


def normalize_meta_dict(
    value: Any,
    modality_key: str,
    context: str,
) -> dict[str, Any] | None:
    schema = get_modality_meta_fields(modality_key)

    if value is None:
        if schema is None:
            return None
        required_keys = ", ".join(sorted(schema))
        raise ValueError(
            f"{context} is required for modality.key={modality_key!r} "
            f"and must contain: {required_keys}"
        )
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")

    normalized = deepcopy(value)
    if "fileTypes" in normalized:
        if "file_types" in normalized:
            raise ValueError(
                f"{context}.fileTypes cannot be used together with "
                f"{context}.file_types"
            )
        normalized["file_types"] = normalized.pop("fileTypes")

    if "dimensions" in normalized:
        validate_dimensions_dict(normalized["dimensions"], f"{context}.dimensions")
    if "file_types" in normalized:
        normalized["file_types"] = _normalize_file_types(
            normalized["file_types"], f"{context}.file_types"
        )

    if schema is not None:
        for key, definition in schema.items():
            if key not in normalized:
                raise ValueError(
                    f"{context}.{key} is required for modality.key={modality_key!r}"
                )
            item = normalized[key]
            if definition.validator is not None:
                err = definition.validator(item)
                if err is not None:
                    raise ValueError(f"{context}.{key} must be {err}")
            elif not isinstance(item, definition.accepted_type):
                raise ValueError(f"{context}.{key} must be {definition.type_label}")

    return normalized


def validate_addon_version(value: Any, context: str = "version") -> None:
    validate_contract_version(value, context)


def register_addon_validator(
    name: str,
    validator: AddonValidator,
    *,
    overwrite: bool = False,
) -> None:
    validate_token(name, "addon")
    if name in _REGISTERED_ADDON_VALIDATORS and not overwrite:
        raise ValueError(
            f"Addon validator for {name!r} already exists; "
            "pass overwrite=True to replace it"
        )
    _REGISTERED_ADDON_VALIDATORS[name] = validator


def get_registered_addon_validators() -> dict[str, AddonValidator]:
    return dict(_REGISTERED_ADDON_VALIDATORS)


def validate_addons(value: Any, context: str = "addons") -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")

    validators = get_registered_addon_validators()
    normalized: dict[str, dict[str, Any]] = {}
    for name, payload in value.items():
        validate_token(name, f"{context} key")
        if not isinstance(payload, dict):
            raise ValueError(f"{context}.{name} must be an object")
        version = payload.get("version")
        validate_addon_version(version, f"{context}.{name}.version")
        copied = deepcopy(payload)
        validator = validators.get(name)
        if validator is not None:
            validator(copied, f"{context}.{name}")
        normalized[name] = copied
    return normalized


def parse_dataset_head(
    value: Any,
    *,
    context: str = "dataset_head",
    required_addons: tuple[str, ...] = (),
) -> "DatasetHeadContract":
    from .contract import DatasetHeadContract

    return DatasetHeadContract.from_mapping(
        value,
        context=context,
        required_addons=required_addons,
    )


def validate_dataset_head(
    value: Any,
    context: str = "dataset_head",
    *,
    required_addons: tuple[str, ...] = (),
) -> None:
    parse_dataset_head(
        value,
        context=context,
        required_addons=required_addons,
    )


def validate_contract_kind(value: Any, context: str = "contract.kind") -> None:
    if value != DATASET_HEAD_KIND:
        raise ValueError(
            f"{context} must be {DATASET_HEAD_KIND!r}, got {value!r}"
        )


def register_namespace_validator(
    name: str,
    validator: AddonValidator,
    *,
    overwrite: bool = False,
) -> None:
    register_addon_validator(name, validator, overwrite=overwrite)


def get_registered_namespace_validators() -> dict[str, AddonValidator]:
    return get_registered_addon_validators()


__all__ = [
    "DATASET_CONTRACT_VERSION",
    "DATASET_HEAD_KIND",
    "get_registered_addon_validators",
    "get_registered_namespace_validators",
    "normalize_meta_dict",
    "parse_dataset_head",
    "register_addon_validator",
    "register_namespace_validator",
    "validate_addon_version",
    "validate_addons",
    "validate_contract_kind",
    "validate_contract_version",
    "validate_dataset_head",
    "validate_dimensions_dict",
    "validate_meta_dict",
    "validate_slot",
    "validate_string_list",
    "validate_token",
]
