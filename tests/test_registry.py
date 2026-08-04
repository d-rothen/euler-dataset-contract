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
