from __future__ import annotations

import pytest

from euler_dataset_contract import (
    DATASET_CONTRACT_VERSION,
    DATASET_HEAD_KIND,
    DatasetHeadContract,
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


def test_build_default_meta_depth() -> None:
    assert build_default_meta("depth") == {
        "radial_depth": False,
        "scale_to_meters": 1.0,
        "range": [0, 65535],
    }


def test_validate_dataset_head_requires_core_sections() -> None:
    with pytest.raises(ValueError, match=r"dataset_head\.modality"):
        validate_dataset_head({
            "contract": {"kind": DATASET_HEAD_KIND, "version": "1.0"},
            "dataset": {"id": "demo", "name": "Demo"},
        })


def test_dataset_head_contract_reads_addons_and_attributes() -> None:
    contract = DatasetHeadContract.from_mapping(_sample_head())

    assert contract.dataset_id == "demo_rgb"
    assert contract.name == "Demo RGB"
    assert contract.type == "rgb"
    assert contract.attributes == {"gt": False}
    assert contract.get_addon("euler_train") == {
        "version": "1.0",
        "used_as": "input",
        "slot": "demo.input.rgb",
    }
    assert contract.to_properties_dict()["meta"]["range"] == [0, 255]


def test_parse_dataset_head_can_require_addon() -> None:
    with pytest.raises(ValueError, match=r"dataset_head\.addons\.euler_loading is required"):
        parse_dataset_head(_sample_head(), required_addons=("euler_loading",))


def test_registered_addon_validator_is_applied() -> None:
    def _validator(value, context):
        if value.get("slot") != "demo.input.rgb":
            raise ValueError(f"{context}.slot mismatch")

    register_addon_validator("euler_train", _validator, overwrite=True)
    validate_dataset_head(_sample_head())


def test_build_meta_schema_contains_shared_file_types() -> None:
    schema = build_meta_schema()
    file_types = schema["properties"]["rgb"]["properties"]["file_types"]

    assert file_types["type"] == "array"
    assert file_types["uniqueItems"] is True
