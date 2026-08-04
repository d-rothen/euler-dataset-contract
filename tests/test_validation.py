from __future__ import annotations

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from euler_dataset_contract import (
    DATASET_CONTRACT_VERSION,
    DATASET_HEAD_KIND,
    DatasetHeadContract,
    build_dataset_head_schema,
    build_default_meta,
    build_meta_schema,
    parse_dataset_head,
    register_addon_validator,
    validate_dataset_head,
)


def _sample_head() -> dict:
    return {
        "contract": {
            "kind": DATASET_HEAD_KIND,
            "version": DATASET_CONTRACT_VERSION,
        },
        "dataset": {
            "id": "demo_rgb",
            "name": "Demo RGB",
            "attributes": {"gt": False},
        },
        "modality": {
            "key": "rgb",
            "meta": {"range": [0, 255]},
        },
        "addons": {
            "euler_train": {
                "version": "1.0",
                "used_as": "input",
                "slot": "demo.input.rgb",
            },
        },
    }


def test_build_default_meta_depth_returns_independent_values() -> None:
    first = build_default_meta("depth")
    second = build_default_meta("depth")

    assert first == {
        "radial_depth": False,
        "scale_to_meters": 1.0,
        "range": [0, 65535],
    }
    assert second == first
    assert first is not second
    assert first["range"] is not second["range"]


def test_build_default_meta_is_none_for_unregistered_modality() -> None:
    assert build_default_meta("custom_signal") is None


def test_validate_dataset_head_requires_core_sections() -> None:
    with pytest.raises(ValueError, match=r"dataset_head\.modality"):
        validate_dataset_head(
            {
                "contract": {"kind": DATASET_HEAD_KIND, "version": "1.0"},
                "dataset": {"id": "demo", "name": "Demo"},
            }
        )


def test_validate_dataset_head_requires_explicit_contract_version() -> None:
    head = _sample_head()
    del head["contract"]["version"]

    with pytest.raises(
        ValueError,
        match=r"dataset_head\.contract\.version must be a non-empty string",
    ):
        validate_dataset_head(head)


@pytest.mark.parametrize("version", ["1", "v1.0", "1.0\n"])
def test_validate_dataset_head_rejects_malformed_contract_version(
    version: str,
) -> None:
    head = _sample_head()
    head["contract"]["version"] = version

    with pytest.raises(ValueError, match="must look like"):
        validate_dataset_head(head)


@pytest.mark.parametrize(
    ("path", "key", "context"),
    [
        ((), "legacy", "dataset_head"),
        (("contract",), "note", "dataset_head.contract"),
        (("dataset",), "source", "dataset_head.dataset"),
        (("modality",), "loader", "dataset_head.modality"),
    ],
)
def test_validate_dataset_head_rejects_unknown_structural_keys(
    path: tuple[str, ...],
    key: str,
    context: str,
) -> None:
    head = _sample_head()
    target = head
    for part in path:
        target = target[part]
    target[key] = "unexpected"

    with pytest.raises(ValueError, match=rf"Unknown {context} key\(s\): {key}"):
        validate_dataset_head(head)


def test_dataset_head_contract_reads_addons_and_attributes() -> None:
    contract = DatasetHeadContract.from_mapping(_sample_head())

    assert contract.dataset_id == "demo_rgb"
    assert contract.name == "Demo RGB"
    assert contract.type == "rgb"
    assert contract.attributes == {"gt": False}
    assert contract.namespace_names == ("euler_train",)
    assert contract.get_addon("euler_train") == {
        "version": "1.0",
        "used_as": "input",
        "slot": "demo.input.rgb",
    }
    assert contract.to_properties_dict()["meta"]["range"] == [0, 255]


def test_dataset_head_contract_round_trip_does_not_alias_input() -> None:
    source = _sample_head()
    contract = parse_dataset_head(source)
    source["dataset"]["attributes"]["gt"] = True
    source["modality"]["meta"]["range"][1] = 1

    serialized = contract.to_mapping()
    assert serialized == _sample_head()

    serialized["addons"]["euler_train"]["used_as"] = "target"
    assert contract.get_addon("euler_train")["used_as"] == "input"


def test_parse_dataset_head_can_require_addon() -> None:
    with pytest.raises(
        ValueError,
        match=r"dataset_head\.addons\.euler_loading is required",
    ):
        parse_dataset_head(_sample_head(), required_addons=("euler_loading",))


def test_registered_addon_validator_is_applied() -> None:
    def _validator(value, context):
        if value.get("enabled") is not True:
            raise ValueError(f"{context}.enabled must be true")

    register_addon_validator("test_extension", _validator, overwrite=True)
    head = _sample_head()
    head["addons"]["test_extension"] = {"version": "1.0", "enabled": False}

    with pytest.raises(
        ValueError,
        match=r"dataset_head\.addons\.test_extension\.enabled must be true",
    ):
        validate_dataset_head(head)


def test_meta_normalization_canonicalizes_file_types() -> None:
    head = _sample_head()
    head["modality"]["meta"]["fileTypes"] = [".PNG", " jpg "]

    contract = parse_dataset_head(head)

    assert contract.meta == {
        "range": [0, 255],
        "file_types": ["jpg", "png"],
    }


def test_rgb_meta_rejects_reversed_range() -> None:
    head = _sample_head()
    head["modality"]["meta"]["range"] = [2, 1]

    with pytest.raises(ValueError, match="min <= max"):
        validate_dataset_head(head)


def test_numeric_meta_fields_reject_booleans() -> None:
    rgb_head = _sample_head()
    rgb_head["modality"]["meta"]["range"] = [False, 255]
    with pytest.raises(ValueError, match="array of 2 numbers"):
        validate_dataset_head(rgb_head)

    depth_head = _sample_head()
    depth_head["modality"] = {
        "key": "depth",
        "meta": {
            "radial_depth": False,
            "scale_to_meters": True,
            "range": [0, 80],
        },
    }
    with pytest.raises(ValueError, match="scale_to_meters must be a number"):
        validate_dataset_head(depth_head)

    segmentation_head = _sample_head()
    segmentation_head["modality"] = {
        "key": "segmentation",
        "meta": {"skyclass": [False, 0, 0]},
    }
    with pytest.raises(ValueError, match="array of 3 integers"):
        validate_dataset_head(segmentation_head)


def test_unregistered_modality_accepts_optional_custom_meta() -> None:
    head = _sample_head()
    head["modality"] = {
        "key": "custom_signal",
        "meta": {"unit": "widgets"},
    }

    assert parse_dataset_head(head).meta == {"unit": "widgets"}


def test_build_meta_schema_contains_shared_file_types() -> None:
    schema = build_meta_schema()
    file_types = schema["properties"]["rgb"]["properties"]["file_types"]

    assert file_types["type"] == "array"
    assert file_types["uniqueItems"] is True


def test_dataset_head_schema_is_valid_and_accepts_runtime_shape() -> None:
    schema = build_dataset_head_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_sample_head())


def test_dataset_head_schema_rejects_blank_dataset_name() -> None:
    schema = build_dataset_head_schema()
    head = _sample_head()
    head["dataset"]["name"] = "   "

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(head)


def test_dataset_head_schema_selects_meta_contract_by_modality_key() -> None:
    schema = build_dataset_head_schema()
    validator = Draft202012Validator(schema)
    depth_head = deepcopy(_sample_head())
    depth_head["modality"] = {
        "key": "depth",
        "meta": {
            "radial_depth": False,
            "scale_to_meters": 1.0,
            "range": [0, 80],
        },
    }
    validator.validate(depth_head)

    del depth_head["modality"]["meta"]["scale_to_meters"]
    with pytest.raises(ValidationError, match="scale_to_meters"):
        validator.validate(depth_head)


def test_dataset_head_schema_allows_custom_modality_metadata() -> None:
    schema = build_dataset_head_schema()
    head = _sample_head()
    head["modality"] = {
        "key": "custom_signal",
        "meta": {"unit": "widgets"},
    }

    Draft202012Validator(schema).validate(head)
