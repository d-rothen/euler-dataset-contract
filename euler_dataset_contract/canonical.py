"""Euler canonical JSON 1: dependency-free semantic hashing (see docs/phase1.md)."""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any

MAX_INTEGER = 2**53 - 1


def canonical_json(value: Any) -> str:
    """Encode JSON values exactly; binary64 fractions use their exact decimal value.

    Objects sort by Unicode scalar value. Strings are not Unicode-normalized.
    Integral floats and negative zero normalize to integers. Non-JSON values,
    lone surrogates, non-finite numbers, and unsafe integers are rejected.
    This primitive has no exclusions; identity-specific callers apply those.
    """
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is str:
        value.encode("utf-8", errors="strict")
        return json.dumps(value, ensure_ascii=False)
    if type(value) is int or type(value) is float:
        if type(value) is float and not math.isfinite(value):
            raise ValueError("Canonical numbers must be finite")
        if value == int(value):
            if abs(value) > MAX_INTEGER:
                raise ValueError(
                    "Canonical integer exceeds the interoperable 53-bit range"
                )
            return str(int(value))
        return format(Decimal.from_float(value), "f").rstrip("0").rstrip(".")
    if type(value) is list:
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Canonical object keys must be strings")
        return (
            "{"
            + ",".join(
                canonical_json(key) + ":" + canonical_json(value[key])
                for key in sorted(value)
            )
            + "}"
        )
    raise ValueError(f"Not a JSON value: {type(value).__name__}")


def canonical_digest(value: Any) -> str:
    """SHA-256 of canonical UTF-8 bytes; not evidence that anything executed."""
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_json(value: str) -> Any:
    """Parse without silently losing duplicate keys or accepting NaN/Infinity."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key!r}")
            result[key] = item
        return result

    def constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON number: {value}")

    result = json.loads(value, object_pairs_hook=pairs, parse_constant=constant)
    canonical_json(result)
    return result
