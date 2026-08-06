"""Pytest plugin exposing the shared conformance corpus.

Registered through the ``pytest11`` entry point, so installing
``euler-dataset-contract[testing]`` is the whole integration for a consuming
repository.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - exercised by the packaging tests, not at runtime
    import pytest
except ModuleNotFoundError as exc:  # pragma: no cover - depends on environment
    raise ImportError(
        "euler_dataset_contract.testing requires pytest, which is not "
        "installed. Install the testing extra with "
        "'pip install euler-dataset-contract[testing]'. The core package "
        "stays dependency-free, so pytest is never installed with it."
    ) from exc

from . import corpus
from .corpus import GoldenHead, InvalidHead

__all__ = [
    "SINGLE_CASE_ARGNAMES",
    "assert_head_roundtrip",
    "conformance_fixtures_root",
    "fixture_index",
    "golden_head_params",
    "golden_heads",
    "invalid_head_params",
    "invalid_heads",
    "modality_inventory",
    "vendored_modality_types",
]


def golden_head_params() -> list[Any]:
    """``pytest.param`` entries for every valid head, for explicit use with
    :func:`pytest.mark.parametrize`."""

    return [pytest.param(case, id=case.name) for case in corpus.golden_heads()]


def invalid_head_params() -> list[Any]:
    """``pytest.param`` entries for every rejection case."""

    return [pytest.param(case, id=case.name) for case in corpus.invalid_heads()]


_SINGLE_CASE_PARAMS = {
    "golden_head": golden_head_params,
    "invalid_head": invalid_head_params,
}

#: Argument names this plugin parametrizes for any test that requests them.
#: A consuming repository must not define its own fixtures with these names.
SINGLE_CASE_ARGNAMES = tuple(_SINGLE_CASE_PARAMS)


def pytest_generate_tests(metafunc: "pytest.Metafunc") -> None:
    """Parametrize tests that ask for a single corpus case.

    A test function taking ``golden_head`` runs once per valid head, and one
    taking ``invalid_head`` runs once per rejection case. Tests that ask for
    the plural fixtures receive the whole corpus instead. Those two argument
    names are reserved by this plugin.
    """

    for argname, build_params in _SINGLE_CASE_PARAMS.items():
        if argname in metafunc.fixturenames:
            metafunc.parametrize(argname, build_params())


@pytest.fixture(scope="session")
def golden_heads() -> tuple[GoldenHead, ...]:
    """Every valid head in the corpus, in manifest order."""

    return corpus.golden_heads()


@pytest.fixture(scope="session")
def invalid_heads() -> tuple[InvalidHead, ...]:
    """Every rejection case in the corpus, each with its expected error."""

    return corpus.invalid_heads()


@pytest.fixture(scope="session")
def modality_inventory() -> dict[str, Any]:
    """The modality inventory shipped with the package."""

    return corpus.modality_inventory()


@pytest.fixture(scope="session")
def vendored_modality_types() -> dict[str, Any]:
    """The vendored copy of euler-loading's emitted modality vocabulary."""

    return corpus.vendored_modality_types()


@pytest.fixture(scope="session")
def fixture_index() -> dict[str, Any]:
    """The corpus manifest."""

    return corpus.fixture_index()


@pytest.fixture(scope="session")
def conformance_fixtures_root():
    """Filesystem root of the conformance corpus."""

    return corpus.fixtures_root()


@pytest.fixture(scope="session")
def assert_head_roundtrip():
    """Callable asserting that a head parses to a stable, idempotent mapping."""

    return corpus.assert_head_roundtrip
