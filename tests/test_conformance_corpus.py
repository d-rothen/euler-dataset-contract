"""The shared corpus must describe this package's actual behaviour.

Consumer repositories assert against the same files through the
``euler_dataset_contract.testing`` plugin, so a corpus that drifts from the
implementation breaks every repository at once. These tests keep the two
together here first.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from euler_dataset_contract import build_dataset_head_schema, parse_dataset_head
from euler_dataset_contract.testing import fixtures_root

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
REGISTERED_MODALITY_KEYS = ("rgb", "depth", "segmentation", "semantic_segmentation")
SHARED_META_FIELDS = ("dimensions", "file_types")


def test_corpus_resolves_to_the_checked_out_files() -> None:
    """A stale installed copy would let the corpus and the code drift apart."""

    assert fixtures_root() == REPOSITORY_ROOT / "fixtures"


def test_every_corpus_file_is_listed_in_the_index(fixture_index) -> None:
    root = fixtures_root()
    listed = {root / entry["head"] for entry in fixture_index["valid_heads"]}
    listed |= {root / entry["canonical"] for entry in fixture_index["valid_heads"]}
    listed |= {root / entry["case"] for entry in fixture_index["invalid_heads"]}
    listed |= {root / entry["path"] for entry in fixture_index["inventory"]}
    listed |= {root / entry["path"] for entry in fixture_index["evidence"]}
    listed |= {root / entry["path"] for entry in fixture_index["descriptors"]}

    on_disk = {path for path in root.rglob("*.json") if path != root / "index.json"}

    assert on_disk == listed


def test_index_entries_are_unique_and_named_after_their_files(
    fixture_index,
) -> None:
    names = [entry["name"] for entry in fixture_index["valid_heads"]]
    names += [entry["name"] for entry in fixture_index["invalid_heads"]]
    assert len(set(names)) == len(names)

    for entry in fixture_index["valid_heads"]:
        assert entry["head"] == f"heads/valid/{entry['name']}.json"
        assert entry["canonical"] == f"heads/canonical/{entry['name']}.json"
        assert entry["description"].strip()
        assert entry["covers"]
    for entry in fixture_index["invalid_heads"]:
        assert entry["case"] == f"heads/invalid/{entry['name']}.json"


def test_corpus_files_are_readable_json_ending_in_a_newline() -> None:
    for path in sorted(fixtures_root().rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n"), path
        json.loads(text)


def test_golden_head_parses_to_its_canonical_form(golden_head) -> None:
    assert parse_dataset_head(golden_head.head).to_mapping() == golden_head.canonical


def test_golden_head_round_trips(golden_head, assert_head_roundtrip) -> None:
    assert assert_head_roundtrip(golden_head) == golden_head.canonical


def test_canonical_form_is_itself_a_valid_head(golden_head) -> None:
    assert parse_dataset_head(golden_head.canonical).to_mapping() == (
        golden_head.canonical
    )


def test_canonical_head_satisfies_generated_schema(golden_head) -> None:
    Draft202012Validator(build_dataset_head_schema()).validate(golden_head.canonical)


def test_invalid_head_schema_behavior_is_explicit(invalid_head) -> None:
    validator = Draft202012Validator(build_dataset_head_schema())
    assert validator.is_valid(invalid_head.head) is invalid_head.schema_valid
    if invalid_head.schema_valid:
        assert invalid_head.schema_note.strip(), invalid_head.name


def test_invalid_head_is_rejected_with_the_stated_error(invalid_head) -> None:
    assert invalid_head.expected_exception == "ValueError"
    with pytest.raises(ValueError) as excinfo:
        parse_dataset_head(invalid_head.head)
    assert invalid_head.expected_error in str(excinfo.value), (
        f"{invalid_head.name}: expected {invalid_head.expected_error!r} in "
        f"{str(excinfo.value)!r}"
    )


def test_corpus_covers_every_registered_modality(golden_heads) -> None:
    covered = {tag for case in golden_heads for tag in case.covers}
    missing = [
        key for key in REGISTERED_MODALITY_KEYS if f"modality_key:{key}" not in covered
    ]
    assert missing == [], f"no valid head covers modality keys: {missing}"


def test_corpus_covers_every_shared_meta_field(golden_heads) -> None:
    covered = {tag for case in golden_heads for tag in case.covers}
    missing = [
        field for field in SHARED_META_FIELDS if f"shared_meta:{field}" not in covered
    ]
    assert missing == [], f"no valid head covers shared meta fields: {missing}"


def test_corpus_covers_the_file_types_normalization_path(golden_heads) -> None:
    cases = [
        case
        for case in golden_heads
        if "normalization:file_types_camel_case" in case.covers
    ]
    assert cases, "the fileTypes to file_types path is not covered"

    for case in cases:
        authored = case.head["modality"]["meta"]
        canonical = case.canonical["modality"]["meta"]
        assert "fileTypes" in authored
        assert "fileTypes" not in canonical
        assert canonical["file_types"] == sorted(canonical["file_types"])
        assert all(value == value.lower() for value in canonical["file_types"])
        assert all(not value.startswith(".") for value in canonical["file_types"])


def test_covers_tags_use_the_declared_vocabulary(
    fixture_index,
    golden_heads,
) -> None:
    prefixes = {tag.split(":", 1)[0] for tag in fixture_index["covers_vocabulary"]}
    for case in golden_heads:
        for tag in case.covers:
            assert tag.split(":", 1)[0] in prefixes, (case.name, tag)


def test_every_invalid_case_documents_itself(invalid_heads) -> None:
    for case in invalid_heads:
        assert case.description.strip(), case.name
        assert case.expected_error.strip(), case.name


def test_dotted_modality_keys_stay_invalid_in_contract_1_0(invalid_heads) -> None:
    """Rich identity must not relax the existing closed 1.0 shape.

    Contract 1.0 keys are tokens. When phase 1 accepts canonical dotted ids it
    must do so in an addon or an explicitly versioned core format.
    """

    case = next(case for case in invalid_heads if case.name == "modality-key-dotted")
    assert "." in case.head["modality"]["key"]
    with pytest.raises(ValueError, match="must contain only letters"):
        parse_dataset_head(case.head)
