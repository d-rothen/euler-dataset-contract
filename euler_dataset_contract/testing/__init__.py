"""Shared conformance fixtures for repositories that consume the contract.

Two layers live here:

* :mod:`euler_dataset_contract.testing.corpus` reads the corpus and the
  modality inventory with no test framework involved. Its helpers are
  re-exported from this module and are safe to call from any code.
* :mod:`euler_dataset_contract.testing.plugin` turns them into pytest
  fixtures. It is registered through the ``pytest11`` entry point, so a
  consuming repository that installs ``euler-dataset-contract[testing]``
  gets ``golden_heads``, ``invalid_heads``, ``modality_inventory`` and
  ``assert_head_roundtrip`` without writing a ``conftest.py``.

The pytest fixtures and the functions re-exported here share names on purpose:
``golden_heads`` is a session fixture inside a pytest run and a plain function
everywhere else. Importing a pytest-only name without pytest installed raises
an :class:`ImportError` naming the extra to install, because the core package
has no dependencies.
"""

from __future__ import annotations

from typing import Any

from .corpus import (
    MODALITY_INVENTORY_FILENAME,
    EvidenceCase,
    GoldenHead,
    InvalidHead,
    assert_head_roundtrip,
    data_root,
    dataset_modality_types,
    descriptor_fixture,
    evidence_cases,
    fixture_index,
    fixtures_root,
    golden_heads,
    invalid_heads,
    loader_observations,
    modality_inventory,
    vendored_modality_types,
)

_PLUGIN_EXPORTS = frozenset(
    {"golden_head_params", "invalid_head_params", "evidence_case_params"}
)

__all__ = [
    "MODALITY_INVENTORY_FILENAME",
    "EvidenceCase",
    "GoldenHead",
    "InvalidHead",
    "assert_head_roundtrip",
    "data_root",
    "dataset_modality_types",
    "descriptor_fixture",
    "evidence_case_params",
    "evidence_cases",
    "fixture_index",
    "fixtures_root",
    "golden_head_params",
    "golden_heads",
    "invalid_head_params",
    "invalid_heads",
    "loader_observations",
    "modality_inventory",
    "vendored_modality_types",
]


def __getattr__(name: str) -> Any:
    if name in _PLUGIN_EXPORTS:
        from . import plugin

        return getattr(plugin, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
