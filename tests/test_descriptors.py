from __future__ import annotations

import copy
import json
import pickle
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator, ValidationError

from euler_dataset_contract import (
    RepresentationAddon,
    RepresentationProfile,
    TransformRecipe,
    TransformsAddon,
    bound_derivation_digest,
    build_descriptor_schema,
    lookup_alias,
    lookup_modality,
    recipe_digest,
    resolve_modality,
    validate_descriptor_shape,
)
from euler_dataset_contract.canonical import (
    canonical_digest,
    canonical_json,
    parse_json,
)
from euler_dataset_contract.testing import descriptor_fixture, fixtures_root


@pytest.fixture
def data():
    return json.loads((fixtures_root() / "descriptors/five-field.json").read_text())


@pytest.mark.parametrize(
    "key,status,identity",
    [
        ("athmospheric_light", "settled", "radiometry.scene.atmospheric_light"),
        ("atmospheric_light", "settled", "radiometry.scene.atmospheric_light"),
        ("sparse_depth", "conditional", None),
        ("spherical_map", "conditional", None),
        ("points_3d", "settled", "geometry.scene.points"),
        ("map_3d", "provisional", "signal.grid.array"),
        ("map_2d", "provisional", "signal.grid.scalar"),
        ("transmission_map", "settled", "radiometry.scene.transmission"),
        (
            "scattering_coefficient",
            "settled",
            "radiometry.scene.scattering_coefficient",
        ),
        ("spectral_map", "unused", None),
        ("calibration", "non_modality", None),
        ("all_intrinsics", "non_modality", None),
        ("unknown", "unknown", None),
    ],
)
def test_registry_diagnostics(key, status, identity):
    from euler_dataset_contract import MODALITY_META_SCHEMAS

    before = dict(MODALITY_META_SCHEMAS)
    result = resolve_modality(key)
    assert (result.legacy_key, result.status, result.modality_id) == (
        key,
        status,
        identity,
    )
    if status != "settled":
        assert result.diagnostics
    assert MODALITY_META_SCHEMAS == before


def test_conditional_and_conflicting_aliases():
    assert (
        resolve_modality(
            "sparse_depth", representation={"form": "point_cloud"}
        ).modality_id
        == "geometry.scene.points"
    )
    assert (
        resolve_modality(
            "sparse_depth", representation={"form": "sparse_raster"}
        ).modality_id
        is None
    )
    assert (
        resolve_modality(
            "spherical_map", representation={"form": "ray_map"}
        ).modality_id
        == "geometry.camera.ray_direction"
    )
    assert (
        resolve_modality("points_3d", representation={"form": "point_cloud"}).status
        == "conflict"
    )
    assert (
        resolve_modality("rgb", declared_id="geometry.camera.depth").status
        == "conflict"
    )
    entry = lookup_modality("signal.grid.array")
    entry["aliases"].clear()
    assert lookup_modality("signal.grid.array")["aliases"] == ["map_3d"]
    alias = lookup_alias("points_3d")
    alias["representation"]["form"] = "cloud"
    assert lookup_alias("points_3d")["representation"]["form"] == "point_map"
    assert lookup_modality("unknown") is None


@pytest.mark.parametrize(
    "name,model,key",
    [
        ("euler_transforms", TransformsAddon, "addon"),
        ("euler_representation", RepresentationAddon, "representation"),
    ],
)
def test_schema_model_roundtrip_and_detachment(data, name, model, key):
    schema = build_descriptor_schema(name)
    Draft202012Validator.check_schema(schema)
    original = copy.deepcopy(data[key])
    Draft202012Validator(schema).validate(original)
    parsed = model.from_mapping(original)
    assert model.from_json(parsed.to_json()) == parsed
    assert pickle.loads(pickle.dumps(parsed)) == parsed
    detached = parsed.to_dict()
    detached["version"] = "99.0"
    assert parsed["version"] == "1.0"
    assert data[key] == original
    with pytest.raises(AttributeError):
        parsed._json = "{}"
    with pytest.raises(AttributeError):
        parsed.definition = "other"


def test_typed_accessors_and_inference_free_profiles(data):
    parsed = TransformsAddon(data["addon"])
    assert parsed.recipe.fields["rgb"].profile.shape == (480, 960, 3)
    assert parsed.recipe.operations[0]["op"] == "euler_loading.resize"
    assert parsed.sources["source_rgb"]["modality_key"] == "rgb"
    profile = data["representation"]["decoded"]
    profile["shape"] = ["H", "W"]
    assert RepresentationProfile(profile).shape == ("H", "W")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(version="1.1"),
        lambda d: d.update(state="materialized"),
        lambda d: d.update(extra=True),
        lambda d: d["recipe"]["operations"][0].update(op="example.unknown"),
        lambda d: d["recipe"]["operations"][0].update(version="1.0.1"),
        lambda d: d["recipe"]["operations"][0]["parameters"].update(size=[0, 3]),
        lambda d: d["recipe"]["operations"][0]["parameters"].update(size=[True, 3]),
        lambda d: d["recipe"]["operations"][0]["parameters"].update(size=[2.5, 3]),
        lambda d: d["recipe"]["operations"][1]["parameters"].update(
            offset=[1, 1]
        ),  # anchor + offset
        lambda d: d["recipe"]["fields"]["depth"]["profile"].pop("depth_kind"),
        lambda d: d["recipe"]["fields"]["ray_map"]["profile"].pop("normalization"),
        lambda d: d["recipe"]["fields"]["intrinsics"]["calibration"].update(
            full_id="leaf"
        ),
        lambda d: d["sources"]["source_depth"].update(verification="content"),
        lambda d: d["sources"]["source_depth"].update(head_digest="sha256:placeholder"),
        lambda d: d["recipe"]["execution"].update(work_dtype="float16"),
        lambda d: d["recipe"]["fields"]["rgb"]["profile"].update(
            layout="CHW", shape=[3, 5]
        ),
        lambda d: d["recipe"]["fields"]["intrinsics"].pop("calibration"),
        lambda d: d["recipe"]["fields"]["valid_mask"]["policy"].update(
            interpolation="bilinear"
        ),
    ],
)
def test_structural_rejections_agree_with_schema(data, mutation):
    value = data["addon"]
    mutation(value)
    with pytest.raises(ValidationError):
        Draft202012Validator(build_descriptor_schema("euler_transforms")).validate(
            value
        )
    with pytest.raises(ValueError):
        validate_descriptor_shape("euler_transforms", value)
    with pytest.raises(ValueError):
        TransformsAddon(value)


@pytest.mark.parametrize(
    "mutation,match",
    [
        (
            lambda d: d.update(required_features=["future.feature"]),
            "Unsupported required features",
        ),
        (
            lambda d: d["recipe"].update(required_features=["future.feature"]),
            "Unsupported required features",
        ),
        (
            lambda d: d["recipe"]["fields"]["rgb"].update(source="missing"),
            "field source",
        ),
        (
            lambda d: d["recipe"]["fields"]["depth"]["profile"].update(
                image_plane="camera_1"
            ),
            "image plane mismatch",
        ),
        (
            lambda d: d["recipe"]["fields"]["depth"]["profile"].update(
                shape=[480, 959]
            ),
            "shape disagrees",
        ),
        (
            lambda d: d["recipe"]["fields"]["depth"]["profile"].update(frame="world"),
            "frame disagrees",
        ),
        (
            lambda d: d["recipe"]["fields"]["intrinsics"]["calibration"].update(
                applies_to=["missing"]
            ),
            "applicability",
        ),
        (
            lambda d: d["recipe"]["operations"][1].update(id="resize_1"),
            "duplicate operation",
        ),
        (
            lambda d: d["recipe"]["operations"][1]["parameters"].update(
                size=[385, 768]
            ),
            "bounds",
        ),
        (
            lambda d: d.update(recipe_digest="sha256:" + "0" * 64),
            "recipe_digest mismatch",
        ),
        (
            lambda d: d["sources"]["source_rgb"]["decoder"].update(
                profile_digest="sha256:" + "0" * 64
            ),
            "decoder profile",
        ),
        (
            lambda d: d["sources"]["source_intrinsics"].update(
                revision="sha256:" + "0" * 64
            ),
            "calibration revision",
        ),
    ],
)
def test_graph_and_capability_validation_is_additional_to_structure(
    data, mutation, match
):
    value = data["addon"]
    mutation(value)
    # JSON Schema has no general foreign-key/digest/executor vocabulary.
    Draft202012Validator(build_descriptor_schema("euler_transforms")).validate(value)
    validate_descriptor_shape("euler_transforms", value)
    with pytest.raises(ValueError, match=match):
        TransformsAddon(value)


def test_recipe_defaults_order_and_identities(data):
    addon = data["addon"]
    recipe = copy.deepcopy(addon["recipe"])
    del recipe["execution"]["device"]
    del recipe["operations"][0]["parameters"]["pixel_centers"]
    del recipe["operations"][1]["parameters"]["anchor"]
    del recipe["fields"]["depth"]["policy"]["invalid_depth"]
    assert recipe_digest(recipe) == addon["recipe_digest"]
    recipe["diagnostics"] = ["relocated today"]
    assert recipe_digest(recipe) == addon["recipe_digest"]
    recipe["operations"] = list(reversed(recipe["operations"]))
    assert recipe_digest(recipe) != addon["recipe_digest"]
    original = bound_derivation_digest(addon, data["source_full_ids"])
    assert original == data["bound_derivation_digest"]
    addon["sources"]["source_rgb"]["locator"] = "/relocated/dataset"
    addon["sources"]["source_rgb"]["diagnostics"] = ["copied today"]
    addon["diagnostics"] = ["example"]
    assert bound_derivation_digest(addon, data["source_full_ids"]) == original
    addon["sources"]["source_rgb"]["revision"] = canonical_digest({"revision": 2})
    assert bound_derivation_digest(addon, data["source_full_ids"]) != original
    assert recipe_digest(addon["recipe"]) == addon["recipe_digest"]
    with pytest.raises(ValueError, match="strict derivation"):
        bound_derivation_digest(addon, data["source_full_ids"], strict=True)
    for source in addon["sources"].values():
        source.update(
            verification="immutable_snapshot", immutable_snapshot="fixture-snapshot-1"
        )
    assert bound_derivation_digest(addon, data["source_full_ids"], strict=True)
    with pytest.raises(ValueError, match="every source"):
        bound_derivation_digest(addon, {})
    ids = dict(data["source_full_ids"], source_intrinsics="/other/camera/calibration")
    with pytest.raises(ValueError, match="qualified calibration"):
        bound_derivation_digest(addon, ids)


def test_canonical_vectors():
    vectors = json.loads(
        (fixtures_root() / "descriptors/canonical-vectors.json").read_text()
    )
    for vector in vectors["vectors"]:
        assert canonical_json(vector["value"]) == vector["canonical"]
        assert canonical_digest(vector["value"]) == vector["digest"]
    assert (
        canonical_json(0.1)
        == "0.1000000000000000055511151231257827021181583404541015625"
    )
    assert canonical_digest({"a": 1, "b": -0.0}) == canonical_digest({"b": 0, "a": 1.0})
    assert canonical_digest([1, 2]) != canonical_digest([2, 1])
    assert canonical_digest("é") != canonical_digest("e\u0301")


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        2**53,
        (1, 2),
        {1: "a"},
        {1, 2},
        "\ud800",
    ],
)
def test_canonical_rejects_ambiguous_values(value):
    with pytest.raises((ValueError, UnicodeError)):
        canonical_json(value)


@pytest.mark.parametrize("value", ['{"x": 1, "x": 2}', "NaN", "Infinity", "1e999"])
def test_json_input_rejects_information_loss(value):
    with pytest.raises(ValueError):
        parse_json(value)


def test_independent_core_and_capable_readers(data, tmp_path):
    path = tmp_path / "addons.json"
    path.write_text(json.dumps(data))
    code = """
import json, sys
from euler_dataset_contract import parse_dataset_head, register_descriptor_validators
d = json.load(open(sys.argv[1]))
head = {'contract': {'kind': 'dataset_head', 'version': '1.0'},
        'dataset': {'id': 'synthetic', 'name': 'Synthetic'}, 'modality': {'key': 'map_3d'},
        'addons': {'euler_transforms': d['addon'], 'euler_representation': d['representation']}}
assert parse_dataset_head(head).to_mapping()['addons'] == head['addons']
head['addons']['euler_transforms']['version'] = '99.0'
assert parse_dataset_head(head).to_mapping()['addons'] == head['addons']
register_descriptor_validators()
register_descriptor_validators()
try:
    parse_dataset_head(head)
except ValueError:
    pass
else:
    raise AssertionError('capable reader accepted unsupported addon')
assert not any(name in sys.modules for name in ('numpy', 'torch', 'PIL', 'pytest'))
"""
    subprocess.run([sys.executable, "-S", "-c", code, str(path)], check=True)


def test_schema_build_returns_detached_data():
    schema = build_descriptor_schema("profile")
    schema["properties"].clear()
    assert build_descriptor_schema("profile")["properties"]


def test_fixture_and_schema_generation_is_current():
    subprocess.run(
        [sys.executable, "scripts/generate_phase1_fixture.py", "--check"], check=True
    )


def test_operation_recipe_json_order_roundtrip(data):
    recipe = TransformRecipe(data["addon"]["recipe"])
    assert [op["id"] for op in recipe.operations] == ["resize_1", "crop_2"]
    assert TransformRecipe.from_json(recipe.to_json()).operations == recipe.operations


@pytest.mark.parametrize(
    "case", descriptor_fixture("rejections")["cases"], ids=lambda case: case["name"]
)
def test_shared_rejection_corpus(data, case):
    value = data["addon"]
    parent = value
    for key in case["path"][:-1]:
        parent = parent[key]
    parent[case["path"][-1]] = case["value"]
    schema = Draft202012Validator(build_descriptor_schema("euler_transforms"))
    assert schema.is_valid(value) is case["schema_valid"]
    with pytest.raises(ValueError, match=case["error"]):
        TransformsAddon(value)


def test_representation_identity_cannot_override_registered_kind(data):
    value = data["representation"]
    value["modality_id"] = "geometry.camera.intrinsics"
    with pytest.raises(ValueError):
        RepresentationAddon(value)
    assert not Draft202012Validator(
        build_descriptor_schema("euler_representation")
    ).is_valid(value)


def test_conflicting_calibration_applicability(data):
    recipe = data["addon"]["recipe"]
    recipe["fields"]["other_intrinsics"] = copy.deepcopy(recipe["fields"]["intrinsics"])
    with pytest.raises(ValueError, match="ambiguous calibration"):
        TransformRecipe(recipe)


def test_descriptor_fixture_values_are_detached():
    value = descriptor_fixture("five-field")
    value["addon"].clear()
    assert descriptor_fixture("five-field")["addon"]
    with pytest.raises(KeyError):
        descriptor_fixture("missing")


def test_json_array_of_pairs_cannot_masquerade_as_an_object(data):
    pairs = list(data["addon"].items())
    with pytest.raises(ValueError, match="must be an object"):
        TransformsAddon.from_json(json.dumps(pairs))
    with pytest.raises(ValueError, match="must be an object"):
        TransformsAddon.from_mapping(pairs)


def test_validator_registration_is_idempotent_and_conflicts_fail(monkeypatch):
    from euler_dataset_contract import (
        register_addon_validator,
        register_descriptor_validators,
        validation,
    )

    monkeypatch.setattr(validation, "_REGISTERED_ADDON_VALIDATORS", {})
    register_descriptor_validators()
    original = validation.get_registered_addon_validators()
    register_descriptor_validators()
    assert validation.get_registered_addon_validators() == original
    register_addon_validator(
        "euler_transforms", lambda value, context: None, overwrite=True
    )
    with pytest.raises(ValueError, match="Conflicting addon"):
        register_descriptor_validators()
