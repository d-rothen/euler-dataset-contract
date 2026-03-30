from __future__ import annotations

import pytest

from euler_dataset_contract import (
    DATASET_CONTRACT_VERSION,
    DatasetHeadContract,
    build_default_meta,
    build_meta_schema,
    normalize_euler_train,
    normalize_meta_dict,
    parse_dataset_head,
    validate_dataset_head,
)


def test_build_default_meta_depth() -> None:
    assert build_default_meta("depth") == {
        "radial_depth": False,
        "scale_to_meters": 1.0,
        "range": [0, 65535],
    }


def test_normalize_meta_dict_accepts_file_types_alias() -> None:
    meta = normalize_meta_dict(
        {"range": [0, 255], "fileTypes": [".PNG", "jpg"]},
        "rgb",
        "meta",
    )

    assert meta == {
        "range": [0, 255],
        "file_types": ["jpg", "png"],
    }


def test_normalize_euler_train_fills_condition_defaults() -> None:
    normalized = normalize_euler_train(
        {"used_as": "condition", "modality_type": "metadata"},
        dataset_name="Weather",
        inferred_hierarchy_scope="scene_camera_frame",
        context="euler_train",
    )

    assert normalized == {
        "used_as": "condition",
        "slot": "weather.condition.metadata",
        "modality_type": "metadata",
        "hierarchy_scope": "scene_camera_frame",
        "applies_to": ["*"],
    }


def test_validate_dataset_head_accepts_contract_version() -> None:
    validate_dataset_head({
        "dataset_contract_version": DATASET_CONTRACT_VERSION,
        "euler_train": {"used_as": "input", "modality_type": "rgb"},
        "meta": {"range": [0, 255]},
    })


def test_validate_dataset_head_requires_meta_for_known_modality() -> None:
    with pytest.raises(ValueError, match=r"dataset\.meta is required"):
        validate_dataset_head({
            "euler_train": {"used_as": "input", "modality_type": "rgb"},
        })


def test_dataset_head_contract_reads_namespaces_and_extras() -> None:
    contract = DatasetHeadContract.from_mapping({
        "dataset_contract_version": DATASET_CONTRACT_VERSION,
        "name": "rgb_train",
        "type": "rgb",
        "properties": {
            "meta": {"range": [0, 255]},
            "euler_train": {"used_as": "input", "modality_type": "rgb"},
            "license": "MIT",
        },
        "euler_loading": {"loader": "images"},
    })

    assert contract.name == "rgb_train"
    assert contract.type == "rgb"
    assert contract.get_namespace("euler_train") == {
        "used_as": "input",
        "modality_type": "rgb",
    }
    assert contract.get_addon_contract("euler_loading") == {"loader": "images"}
    assert contract.extras == {"license": "MIT"}
    assert contract.to_properties_dict()["meta"]["range"] == [0, 255]


def test_parse_dataset_head_can_require_namespace() -> None:
    with pytest.raises(ValueError, match=r"dataset\.euler_loading is required"):
        parse_dataset_head(
            {
                "type": "rgb",
                "meta": {"range": [0, 255]},
                "euler_train": {"used_as": "input", "modality_type": "rgb"},
            },
            required_namespaces=("euler_loading",),
        )


def test_build_meta_schema_contains_shared_file_types() -> None:
    schema = build_meta_schema()
    file_types = schema["properties"]["rgb"]["properties"]["file_types"]

    assert file_types["type"] == "array"
    assert file_types["uniqueItems"] is True
