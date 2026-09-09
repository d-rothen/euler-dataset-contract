"""Evidence-based identity lookups. Consulting these never registers legacy meta."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def _inventory() -> dict[str, Any]:
    return json.loads(
        (Path(__file__).parent / "data/modality-inventory-1.0.json").read_text()
    )


def lookup_modality(identity: str) -> dict[str, Any] | None:
    """Return a detached registry record, or None. No axes/decoder are inferred."""
    return deepcopy(_inventory()["modalities"].get(identity))


def lookup_alias(key: str) -> dict[str, Any] | None:
    """Look up the exact persisted spelling, without case/spelling normalization."""
    return deepcopy(_inventory()["aliases"].get(key))


@dataclass(frozen=True)
class ModalityResolution:
    legacy_key: str
    modality_id: str | None
    candidate_id: str | None
    status: str
    diagnostics: tuple[str, ...]


def resolve_modality(
    key: str,
    *,
    representation: dict[str, Any] | None = None,
    declared_id: str | None = None,
) -> ModalityResolution:
    """Resolve only supported aliases; report missing evidence and conflicts.

    Provisional identities are returned with diagnostics. Conditional aliases
    return only a candidate until their representation conditions are supplied.
    A declaration cannot override a known meaning or waive its conditions.
    """
    inventory = _inventory()
    for section, status in (
        ("unused_names", "unused"),
        ("non_modalities", "non_modality"),
    ):
        if key in inventory[section]:
            entry = inventory[section][key]
            return ModalityResolution(
                key,
                None,
                None,
                status,
                (entry.get("note", entry.get("description", status)),),
            )
    alias = lookup_alias(key)
    if alias is None:
        return ModalityResolution(
            key,
            None,
            declared_id,
            "unknown",
            (
                f"No registered alias for {key!r}; declare and validate its representation locally.",
            ),
        )
    candidate = alias["id"]
    diagnostics = []
    if declared_id is not None and declared_id != candidate:
        return ModalityResolution(
            key,
            None,
            candidate,
            "conflict",
            (
                f"Declared identity {declared_id!r} conflicts with {key!r} -> {candidate!r}.",
            ),
        )
    supplied = representation or {}
    for path, expected in alias.get("conditions", {}).items():
        name = path.removeprefix("representation.")
        if supplied.get(name) != expected:
            diagnostics.append(
                f"Declare {path}={expected!r} to resolve {key!r}; got {supplied.get(name)!r}."
            )
    if diagnostics:
        return ModalityResolution(
            key, None, candidate, "conditional", tuple(diagnostics)
        )
    for name, expected in alias.get("representation", {}).items():
        if name in supplied and supplied[name] != expected:
            return ModalityResolution(
                key,
                None,
                candidate,
                "conflict",
                (
                    f"{key!r} requires representation.{name}={expected!r}; got {supplied[name]!r}.",
                ),
            )
    if alias.get("note"):
        diagnostics.append(alias["note"])
    return ModalityResolution(
        key, candidate, candidate, alias["status"], tuple(diagnostics)
    )
