"""Access to the shared conformance corpus and the modality inventory.

This module deliberately does not import :mod:`pytest`. It is the layer a
non-pytest consumer, a script, or another test framework can use directly.
The pytest fixtures in :mod:`euler_dataset_contract.testing.plugin` are a thin
wrapper around it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "EvidenceCase",
    "GoldenHead",
    "InvalidHead",
    "MODALITY_INVENTORY_FILENAME",
    "assert_head_roundtrip",
    "data_root",
    "dataset_modality_types",
    "evidence_cases",
    "fixture_index",
    "fixtures_root",
    "golden_heads",
    "invalid_heads",
    "loader_observations",
    "modality_inventory",
    "vendored_modality_types",
]

MODALITY_INVENTORY_FILENAME = "modality-inventory-1.0.json"

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class GoldenHead:
    """A dataset head that must parse, with its expected canonical form."""

    name: str
    description: str
    covers: tuple[str, ...]
    head: dict[str, Any]
    canonical: dict[str, Any]
    path: Path
    canonical_path: Path

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.name


@dataclass(frozen=True)
class InvalidHead:
    """A dataset head that must be rejected, with the error it must produce."""

    name: str
    description: str
    expected_exception: str
    expected_error: str
    head: dict[str, Any]
    path: Path
    schema_valid: bool = False
    schema_note: str = ""

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.name


@dataclass(frozen=True)
class EvidenceCase:
    """Phase 0 test data, not an executable dataset-head extension.

    ``kind`` selects a family such as preprocessing, decoding, or persistence.
    Reference answers and observed legacy behavior are labeled in the payload.
    Consumers execute their own implementations against these detached values.
    """

    name: str
    kind: str
    description: str
    payload: dict[str, Any]
    path: Path

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.name


def data_root() -> Path:
    """Directory holding the data files shipped inside the package."""

    return _PACKAGE_ROOT / "data"


def fixtures_root() -> Path:
    """Directory holding the conformance corpus.

    The corpus lives at the repository root so that non-Python consumers can
    read it from a checkout. Wheels carry a copy inside the package, which is
    preferred when present.
    """

    candidates = (_PACKAGE_ROOT / "_fixtures", _PACKAGE_ROOT.parent / "fixtures")
    for candidate in candidates:
        if (candidate / "index.json").is_file():
            return candidate
    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(
        "The euler-dataset-contract conformance corpus is not installed. "
        f"Looked for an index.json in: {searched}"
    )


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=None)
def _cached_index() -> dict[str, Any]:
    return _read_json(fixtures_root() / "index.json")


@lru_cache(maxsize=None)
def _cached_modality_inventory() -> dict[str, Any]:
    path = data_root() / MODALITY_INVENTORY_FILENAME
    if not path.is_file():
        raise FileNotFoundError(
            "The euler-dataset-contract modality inventory is missing from the "
            f"installed package. Expected it at: {path}"
        )
    return _read_json(path)


@lru_cache(maxsize=None)
def _cached_vendored_modality_types() -> dict[str, Any]:
    return _cached_inventory("euler-loading-modality-types")


@lru_cache(maxsize=None)
def _cached_inventory(name: str) -> dict[str, Any]:
    for entry in _cached_index()["inventory"]:
        if entry["name"] == name:
            return _read_json(fixtures_root() / entry["path"])
    raise KeyError(f"The fixture index has no {name!r} inventory entry")


@lru_cache(maxsize=None)
def _cached_evidence_cases() -> tuple[EvidenceCase, ...]:
    cases = []
    # A missing section is an incomplete installation, not an empty corpus.
    for entry in _cached_index()["evidence"]:
        path = fixtures_root() / entry["path"]
        cases.append(
            EvidenceCase(
                name=entry["name"],
                kind=entry["kind"],
                description=entry["description"],
                payload=_read_json(path),
                path=path,
            )
        )
    return tuple(cases)


@lru_cache(maxsize=None)
def _cached_golden_heads() -> tuple[GoldenHead, ...]:
    root = fixtures_root()
    cases = []
    for entry in _cached_index()["valid_heads"]:
        head_path = root / entry["head"]
        canonical_path = root / entry["canonical"]
        cases.append(
            GoldenHead(
                name=entry["name"],
                description=entry.get("description", ""),
                covers=tuple(entry.get("covers", ())),
                head=_read_json(head_path),
                canonical=_read_json(canonical_path),
                path=head_path,
                canonical_path=canonical_path,
            )
        )
    return tuple(cases)


@lru_cache(maxsize=None)
def _cached_invalid_heads() -> tuple[InvalidHead, ...]:
    root = fixtures_root()
    cases = []
    for entry in _cached_index()["invalid_heads"]:
        case_path = root / entry["case"]
        payload = _read_json(case_path)
        cases.append(
            InvalidHead(
                name=entry["name"],
                description=payload.get("description", ""),
                expected_exception=payload.get("expected_exception", "ValueError"),
                expected_error=payload["expected_error"],
                head=payload["head"],
                path=case_path,
                schema_valid=payload.get("schema_valid", False),
                schema_note=payload.get("schema_note", ""),
            )
        )
    return tuple(cases)


def fixture_index() -> dict[str, Any]:
    """The corpus manifest as a detached mapping."""

    return deepcopy(_cached_index())


def modality_inventory() -> dict[str, Any]:
    """The shipped modality inventory as a detached mapping."""

    return deepcopy(_cached_modality_inventory())


def vendored_modality_types() -> dict[str, Any]:
    """The vendored copy of euler-loading's emitted modality vocabulary."""

    return deepcopy(_cached_vendored_modality_types())


def dataset_modality_types() -> dict[str, Any]:
    """Operator-reported dataset vocabulary, including unused names."""

    return deepcopy(_cached_inventory("dataset-modality-types"))


def loader_observations() -> dict[str, Any]:
    """Source-derived CPU/GPU declarations, not verified decoded profiles."""

    return deepcopy(_cached_inventory("loader-observations"))


def evidence_cases(kind: str | None = None) -> tuple[EvidenceCase, ...]:
    """Detached Phase 0 evidence, in manifest order, optionally filtered.

    Reject an unknown kind so a typo cannot silently run zero conformance cases.
    """

    cases = _cached_evidence_cases()
    if kind is not None:
        known = {case.kind for case in cases}
        if kind not in known:
            raise ValueError(
                f"Unknown evidence kind {kind!r}; available: {sorted(known)}"
            )
        cases = tuple(case for case in cases if case.kind == kind)
    return tuple(deepcopy(case) for case in cases)


def golden_heads() -> tuple[GoldenHead, ...]:
    """Every valid head in the corpus, in manifest order."""

    return tuple(deepcopy(case) for case in _cached_golden_heads())


def invalid_heads() -> tuple[InvalidHead, ...]:
    """Every rejection case in the corpus, in manifest order."""

    return tuple(deepcopy(case) for case in _cached_invalid_heads())


def assert_head_roundtrip(head: Any) -> dict[str, Any]:
    """Assert that parsing and serializing ``head`` is stable and idempotent.

    Accepts a head mapping or a :class:`GoldenHead`. Returns the canonical
    mapping. Raises :class:`AssertionError` when any of the following does not
    hold:

    * serializing the same parsed contract twice produces equal mappings;
    * the serialized mapping is detached, so mutating it cannot reach back into
      the contract;
    * parsing the serialized mapping again produces the same mapping, meaning
      normalization has reached a fixed point.
    """

    from ..validation import parse_dataset_head

    if isinstance(head, GoldenHead):
        head = head.head
    if not isinstance(head, Mapping):
        raise AssertionError(f"head must be a mapping, got {type(head).__name__}")

    source = deepcopy(dict(head))
    contract = parse_dataset_head(source)

    canonical = contract.to_mapping()
    again = contract.to_mapping()
    if canonical != again:
        raise AssertionError(
            "to_mapping() is not stable: two calls on one contract disagree.\n"
            f"first:  {canonical!r}\nsecond: {again!r}"
        )
    if canonical is again:
        raise AssertionError("to_mapping() returned the same object twice")

    # Mutating a serialized copy must not reach back into the contract.
    again["dataset"]["name"] = "mutated by assert_head_roundtrip"
    if contract.to_mapping() != canonical:
        raise AssertionError(
            "to_mapping() is not detached: mutating the result changed the contract"
        )

    reparsed = parse_dataset_head(deepcopy(canonical)).to_mapping()
    if reparsed != canonical:
        raise AssertionError(
            "parsing is not idempotent: the canonical form does not survive a "
            f"second parse.\nfirst:  {canonical!r}\nsecond: {reparsed!r}"
        )

    if source != deepcopy(dict(head)):
        raise AssertionError("parsing mutated the head it was given")

    return canonical
