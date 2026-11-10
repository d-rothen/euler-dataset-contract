from __future__ import annotations

import pytest

from euler_dataset_contract import (
    MODALITY_META_SCHEMAS,
    MetaFieldDefinition,
    build_default_meta,
    build_meta_schema,
    register_modality_meta_fields,
)


def test_registration_updates_runtime_schema_and_legacy_view() -> None:
    register_modality_meta_fields(
        "test_signal",
        {
            "gain": MetaFieldDefinition(
                accepted_type=float,
                type_label="a number",
                description="Decoded signal gain.",
                default=1.0,
            )
        },
        overwrite=True,
    )

    assert build_default_meta("test_signal") == {"gain": 1.0}
    assert "gain" in MODALITY_META_SCHEMAS["test_signal"]
    assert build_meta_schema()["properties"]["test_signal"]["required"] == [
        "gain"
    ]


@pytest.mark.parametrize("modality_key", ["camera.intrinsics", "9depth", ""])
def test_registration_rejects_invalid_modality_key(modality_key: str) -> None:
    with pytest.raises(ValueError, match="modality_key must contain"):
        register_modality_meta_fields(modality_key, {})


def test_registration_requires_field_definitions() -> None:
    with pytest.raises(TypeError, match="must be a MetaFieldDefinition"):
        register_modality_meta_fields(
            "invalid_definition",
            {"gain": object()},  # type: ignore[dict-item]
        )


def _head(key, meta=None):
    head = {
        "contract": {"kind": "dataset_head", "version": "1.0"},
        "dataset": {"id": "demo", "name": "Demo"},
        "modality": {"key": key},
    }
    if meta is not None:
        head["modality"]["meta"] = meta
    return head


def test_optional_fields_are_checked_only_when_present() -> None:
    from euler_dataset_contract import parse_dataset_head

    register_modality_meta_fields(
        "test_optional",
        {
            "unit": MetaFieldDefinition(
                accepted_type=str,
                type_label="a string",
                description="Unit.",
                required=False,
            )
        },
        overwrite=True,
    )
    parse_dataset_head(_head("test_optional"))  # meta may be omitted entirely
    parse_dataset_head(_head("test_optional", {}))
    parse_dataset_head(_head("test_optional", {"unit": "m"}))
    with pytest.raises(ValueError, match=r"meta\.unit must be a string"):
        parse_dataset_head(_head("test_optional", {"unit": 3}))
    assert build_default_meta("test_optional") == {}
    assert MODALITY_META_SCHEMAS["test_optional"] == {}
    schema = build_meta_schema()["properties"]["test_optional"]
    assert schema["required"] == [] and "unit" in schema["properties"]


def test_copies_of_a_field_without_default_keep_having_none() -> None:
    from copy import deepcopy

    from euler_dataset_contract import get_modality_meta_fields

    definition = MetaFieldDefinition(accepted_type=str, type_label="a string", description="x")
    assert not deepcopy(definition).has_default
    assert not get_modality_meta_fields("intrinsics")["camera_model"].has_default


@pytest.mark.parametrize(
    "key",
    ["camera_extrinsics", "extrinsics", "lidar_to_gnss", "lidar_pose"],
)
def test_transform_keys_share_the_transform_fields(key: str) -> None:
    from euler_dataset_contract import parse_dataset_head

    parse_dataset_head(_head(key))
    parse_dataset_head(
        _head(key, {"source_frame": "lidar", "target_frame": "camera", "direction": "target_from_source"})
    )
    with pytest.raises(ValueError, match="direction must be one of"):
        parse_dataset_head(_head(key, {"direction": "lidar_to_camera"}))


@pytest.mark.parametrize("key", ["points_3d", "point_cloud", "lidar_point_cloud", "sparse_depth"])
def test_point_keys_share_the_point_fields(key: str) -> None:
    from euler_dataset_contract import parse_dataset_head

    parse_dataset_head(_head(key))
    parse_dataset_head(
        _head(key, {"representation": "point_cloud", "columns": ["x", "y", "z"], "coordinate_unit": "meters"})
    )
    with pytest.raises(ValueError, match="coordinate_unit must be a non-empty string"):
        parse_dataset_head(_head(key, {"coordinate_unit": " "}))
