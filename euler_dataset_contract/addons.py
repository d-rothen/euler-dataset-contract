"""Validators for the ecosystem's own addons, shared by every package.

A dataset head names its euler-loading decoder in ``addons.euler_loading``.
euler-loading used to own these rules and registered them only when it was
imported, so a head ds-crawler accepted could still be rejected when the
dataset was loaded. The rules live here so producers (ds-crawler,
euler-known-datasets) and euler-loading apply the same ones.

Registration stays explicit, as for the descriptor validators: call
:func:`register_euler_loading_addon_validator` once per process. It is
idempotent and never replaces a validator that is already registered for
``euler_loading``, so an euler-loading release that extends its addon before
this package does keeps its own rules.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .validation import (
    get_registered_addon_validators,
    register_addon_validator,
    validate_addon_version,
    validate_slot,
    validate_string_list,
    validate_token,
)

EULER_LOADING_ADDON = "euler_loading"

#: Experiment roles a modality can take.
USED_AS_VALUES = ("condition", "input", "output", "target")

#: Role fields shared by ecosystem addons (``euler_loading``, ``euler_train``).
ROLE_KEYS = ("used_as", "slot", "task", "hierarchy_scope", "applies_to")

_EULER_LOADING_KEYS = frozenset(
    ("version", *ROLE_KEYS, "loader", "function", "writer_function")
)


def validate_addon_roles(value: Mapping[str, Any], context: str) -> None:
    """Validate the shared role fields of an addon payload.

    ``used_as`` is one of :data:`USED_AS_VALUES`, ``slot`` a dotted slot name,
    ``task`` and ``hierarchy_scope`` tokens, and ``applies_to`` a list of
    tokens or ``"*"``. ``hierarchy_scope`` and ``applies_to`` describe where a
    condition applies, so they require ``used_as: condition``.
    """
    used_as = value.get("used_as")
    if used_as is not None:
        if not isinstance(used_as, str) or not used_as:
            raise ValueError(f"{context}.used_as must be a non-empty string")
        if used_as not in USED_AS_VALUES:
            allowed = ", ".join(sorted(USED_AS_VALUES))
            raise ValueError(
                f"{context}.used_as must be one of {{{allowed}}}, got {used_as!r}"
            )

    slot = value.get("slot")
    if slot is not None:
        validate_slot(slot, f"{context}.slot")

    task = value.get("task")
    if task is not None:
        validate_token(task, f"{context}.task")

    hierarchy_scope = value.get("hierarchy_scope")
    applies_to = value.get("applies_to")
    if hierarchy_scope is not None or applies_to is not None:
        if used_as != "condition":
            raise ValueError(
                f"{context}.hierarchy_scope and {context}.applies_to are only "
                "allowed when used_as is 'condition'"
            )
        if hierarchy_scope is not None:
            validate_token(hierarchy_scope, f"{context}.hierarchy_scope")
        if applies_to is not None:
            validate_string_list(
                applies_to,
                f"{context}.applies_to",
                allow_wildcard=True,
            )


def validate_euler_loading_addon(value: Any, context: str) -> None:
    """Validate an ``addons.euler_loading`` payload.

    Keys are limited to ``version``, the role fields, ``loader``, ``function``
    and ``writer_function``. ``loader`` and ``function`` are tokens set
    together, naming the decoder module and the callable in it;
    ``writer_function`` optionally names the writer.
    """
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")

    unknown = sorted(set(value.keys()) - _EULER_LOADING_KEYS)
    if unknown:
        raise ValueError(f"Unknown {context} key(s): {', '.join(unknown)}")

    validate_addon_version(value.get("version"), f"{context}.version")
    validate_addon_roles(value, context)

    loader = value.get("loader")
    function = value.get("function")
    if loader is not None:
        validate_token(loader, f"{context}.loader")
    if function is not None:
        validate_token(function, f"{context}.function")
    if (loader is None) != (function is None):
        raise ValueError(
            f"{context}.loader and {context}.function must either both be set "
            "or both be omitted"
        )

    writer_function = value.get("writer_function")
    if writer_function is not None:
        validate_token(writer_function, f"{context}.writer_function")


def register_euler_loading_addon_validator() -> bool:
    """Register :func:`validate_euler_loading_addon` unless a validator exists.

    Returns ``True`` when this call registered it. Safe to call any number of
    times and from several packages.
    """
    if EULER_LOADING_ADDON in get_registered_addon_validators():
        return False
    register_addon_validator(EULER_LOADING_ADDON, validate_euler_loading_addon)
    return True


__all__ = [
    "EULER_LOADING_ADDON",
    "ROLE_KEYS",
    "USED_AS_VALUES",
    "register_euler_loading_addon_validator",
    "validate_addon_roles",
    "validate_euler_loading_addon",
]
