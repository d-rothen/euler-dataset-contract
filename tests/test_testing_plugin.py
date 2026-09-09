"""The plugin is the integration surface other repositories install.

Two properties matter beyond the fixtures working: the core package must stay
dependency-free, and a consumer without pytest must get an actionable message
rather than a traceback from an unexpected import.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from euler_dataset_contract.testing import EvidenceCase, GoldenHead, InvalidHead, corpus
from euler_dataset_contract.testing import assert_head_roundtrip as roundtrip_helper

BLOCK_PYTEST = """
import sys


class _BlockPytest:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {"pytest", "numpy", "torch", "PIL", "cv2"}:
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None


sys.meta_path.insert(0, _BlockPytest())
"""


def _run(source: str, *, without_pytest: bool = False) -> subprocess.CompletedProcess:
    script = textwrap.dedent(source)
    if without_pytest:
        script = BLOCK_PYTEST + script
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


def test_importing_the_core_package_does_not_import_pytest() -> None:
    result = _run(
        """
        import sys

        import euler_dataset_contract

        assert "pytest" not in sys.modules, sorted(
            name for name in sys.modules if "pytest" in name
        )
        print("clean")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_core_package_imports_without_pytest_installed() -> None:
    result = _run(
        """
        import euler_dataset_contract
        from euler_dataset_contract import parse_dataset_head

        parse_dataset_head(
            {
                "contract": {"kind": "dataset_head", "version": "1.0"},
                "dataset": {"id": "demo", "name": "Demo"},
                "modality": {"key": "rgb", "meta": {"range": [0, 255]}},
            }
        )
        print("clean")
        """,
        without_pytest=True,
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_corpus_layer_works_without_pytest_installed() -> None:
    result = _run(
        """
        from euler_dataset_contract.testing import (
            golden_heads, modality_inventory, evidence_cases,
            dataset_modality_types, loader_observations,
        )

        assert golden_heads()
        assert modality_inventory()["contract"]["kind"] == "modality_inventory"
        assert evidence_cases()
        assert dataset_modality_types()
        assert loader_observations()
        print("clean")
        """,
        without_pytest=True,
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_plugin_import_without_pytest_names_the_extra() -> None:
    result = _run(
        """
        try:
            import euler_dataset_contract.testing.plugin
        except ImportError as exc:
            print(exc)
        else:
            raise AssertionError("importing the plugin should have failed")
        """,
        without_pytest=True,
    )
    assert result.returncode == 0, result.stderr
    assert "euler-dataset-contract[testing]" in result.stdout
    assert "requires pytest" in result.stdout


def test_pytest_only_attribute_without_pytest_names_the_extra() -> None:
    result = _run(
        """
        import euler_dataset_contract.testing as testing

        try:
            testing.golden_head_params
        except ImportError as exc:
            print(exc)
        else:
            raise AssertionError("accessing a pytest-only helper should have failed")
        """,
        without_pytest=True,
    )
    assert result.returncode == 0, result.stderr
    assert "euler-dataset-contract[testing]" in result.stdout


def test_plugin_is_registered_through_the_entry_point(pytestconfig) -> None:
    from euler_dataset_contract.testing import plugin

    assert pytestconfig.pluginmanager.is_registered(plugin), (
        "the pytest11 entry point did not load the plugin"
    )


def test_single_case_helpers_expose_one_param_per_case() -> None:
    """``golden_head`` and ``invalid_head`` fan out one test per case.

    The hook itself is exercised by ``tests/test_conformance_corpus.py``, whose
    tests take the singular fixtures and would fail to collect if the
    parametrization stopped working.
    """

    from euler_dataset_contract.testing import (
        evidence_case_params,
        golden_head_params,
        invalid_head_params,
    )

    valid = golden_head_params()
    invalid = invalid_head_params()

    assert [param.id for param in valid] == [
        case.name for case in corpus.golden_heads()
    ]
    assert [param.id for param in invalid] == [
        case.name for case in corpus.invalid_heads()
    ]
    assert [param.id for param in evidence_case_params()] == [
        case.name for case in corpus.evidence_cases()
    ]
    assert len(evidence_case_params("preprocessing")) == 2


def test_corpus_objects_are_detached() -> None:
    first = corpus.golden_heads()[0]
    first.head["dataset"]["name"] = "mutated"
    assert corpus.golden_heads()[0].head["dataset"]["name"] != "mutated"

    inventory = corpus.modality_inventory()
    inventory["modalities"].clear()
    assert corpus.modality_inventory()["modalities"]


def test_fixtures_expose_the_documented_types(
    golden_heads,
    invalid_heads,
    modality_inventory,
    evidence_cases,
    dataset_modality_types,
    loader_observations,
) -> None:
    assert all(isinstance(case, GoldenHead) for case in golden_heads)
    assert all(isinstance(case, InvalidHead) for case in invalid_heads)
    assert modality_inventory["contract"]["version"] == "1.0"
    assert all(isinstance(case, EvidenceCase) for case in evidence_cases)
    assert dataset_modality_types == corpus.dataset_modality_types()
    assert loader_observations == corpus.loader_observations()


def test_assert_head_roundtrip_rejects_what_is_not_a_head() -> None:
    with pytest.raises(AssertionError, match="must be a mapping"):
        roundtrip_helper("not a head")

    with pytest.raises(ValueError, match=r"dataset_head\.modality"):
        roundtrip_helper(
            {
                "contract": {"kind": "dataset_head", "version": "1.0"},
                "dataset": {"id": "demo", "name": "Demo"},
            }
        )
