from __future__ import annotations

import pytest

from euler_dataset_contract import (
    parse_dataset_head,
    register_addon_validator,
    register_euler_loading_addon_validator,
    validate_addon_roles,
    validate_euler_loading_addon,
    validation,
)


@pytest.fixture
def empty_registry(monkeypatch):
    monkeypatch.setattr(validation, "_REGISTERED_ADDON_VALIDATORS", {})


def _head(addon):
    return {
        "contract": {"kind": "dataset_head", "version": "1.0"},
        "dataset": {"id": "demo", "name": "Demo"},
        "modality": {"key": "rgb", "meta": {"range": [0, 255]}},
        "addons": {"euler_loading": addon},
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"version": "1.0"},
        {"version": "1.0", "loader": "nuscenes", "function": "read_extrinsics"},
        {"version": "1.0", "loader": "vkitti2", "function": "rgb", "writer_function": "write_rgb"},
        {"version": "1.0", "used_as": "input", "slot": "dehaze.input.rgb", "task": "dehaze"},
        {
            "version": "1.0",
            "used_as": "condition",
            "hierarchy_scope": "scene_camera",
            "applies_to": ["rgb", "*"],
        },
    ],
)
def test_valid_euler_loading_payloads(payload):
    validate_euler_loading_addon(payload, "addons.euler_loading")


@pytest.mark.parametrize(
    "payload, message",
    [
        ("vkitti2", "must be an object"),
        ({"version": "1.0", "modality_type": "rgb"}, "Unknown addons.euler_loading key"),
        ({"version": "one"}, "version"),
        ({"version": "1.0", "loader": "vkitti2"}, "both be set"),
        ({"version": "1.0", "loader": "vkitti-2", "function": "rgb"}, "loader"),
        ({"version": "1.0", "writer_function": "write rgb"}, "writer_function"),
        ({"version": "1.0", "used_as": "label"}, "used_as must be one of"),
        ({"version": "1.0", "slot": "flat"}, "slot"),
        ({"version": "1.0", "hierarchy_scope": "scene_camera"}, "only allowed when used_as"),
        ({"version": "1.0", "used_as": "input", "applies_to": ["rgb"]}, "only allowed when used_as"),
        ({"version": "1.0", "used_as": "condition", "applies_to": []}, "cannot be empty"),
    ],
)
def test_invalid_euler_loading_payloads(payload, message):
    with pytest.raises(ValueError, match=message):
        validate_euler_loading_addon(payload, "addons.euler_loading")


def test_roles_are_reusable_by_other_addons():
    validate_addon_roles({"used_as": "target", "slot": "a.b"}, "addons.euler_train")
    with pytest.raises(ValueError, match="addons.euler_train.used_as"):
        validate_addon_roles({"used_as": "label"}, "addons.euler_train")


def test_heads_are_checked_once_registered(empty_registry):
    bad = _head({"version": "1.0", "hierarchy_scope": "scene_camera"})
    parse_dataset_head(bad)  # nothing registered: payload fields are not checked
    assert register_euler_loading_addon_validator() is True
    with pytest.raises(ValueError, match=r"dataset_head\.addons\.euler_loading\.hierarchy_scope"):
        parse_dataset_head(bad)
    parse_dataset_head(_head({"version": "1.0", "loader": "vkitti2", "function": "rgb"}))


def test_registration_is_idempotent_and_keeps_an_existing_validator(empty_registry):
    assert register_euler_loading_addon_validator() is True
    assert register_euler_loading_addon_validator() is False
    assert validation.get_registered_addon_validators()["euler_loading"] is validate_euler_loading_addon

    def extended(value, context):  # e.g. a newer euler-loading accepting a new key
        pass

    register_addon_validator("euler_loading", extended, overwrite=True)
    assert register_euler_loading_addon_validator() is False
    assert validation.get_registered_addon_validators()["euler_loading"] is extended
