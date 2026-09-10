from copy import deepcopy

import jsonschema
import pytest

from euler_dataset_contract import (
    ArtifactReceipt,
    ExecutionReceipt,
    MaterializedTransforms,
    OutputPlan,
    TransformsAddon,
    build_descriptor_schema,
    parse_dataset_head,
    register_descriptor_validators,
    resolve_receipt,
    validate_artifact_receipt,
    validate_descriptor_shape,
    validate_execution,
)
from euler_dataset_contract.testing import descriptor_fixture, golden_heads


@pytest.fixture
def vector():
    return descriptor_fixture("phase2-five-field")


@pytest.mark.parametrize(
    "name,key,model",
    [
        ("output_plan", "plan", OutputPlan),
        ("execution_receipt", "execution", ExecutionReceipt),
        ("artifact_receipt", "receipt", ArtifactReceipt),
        ("materialized_transforms", "addon", MaterializedTransforms),
    ],
)
def test_phase2_runtime_schema_and_detachment(vector, name, key, model):
    raw = vector[key]
    jsonschema.Draft202012Validator(build_descriptor_schema(name)).validate(raw)
    validate_descriptor_shape(name, raw)
    value = model(raw)
    detached = value.to_dict()
    detached["version"] = "unknown"
    assert value == model.from_json(value.to_json()) and value["version"] == "2.0"


def test_bound_receipts_locations(vector):
    validate_execution(vector["execution"], vector["descriptor"])
    validate_artifact_receipt(
        vector["receipt"], vector["plan"], full_id="/changed/frame_0"
    )
    assert resolve_receipt(vector["inline"]) == resolve_receipt(
        vector["sidecar"], vector["records"].__getitem__
    )
    corrupt = deepcopy(vector["records"])
    next(iter(corrupt.values()))["variant_id"] = "corrupt"
    with pytest.raises(ValueError, match="digest mismatch"):
        resolve_receipt(vector["sidecar"], corrupt.__getitem__)
    conflict = {**vector["inline"], "record": vector["sidecar"]["record"]}
    with pytest.raises(ValueError):
        resolve_receipt(conflict, vector["records"].__getitem__)


@pytest.mark.parametrize(
    "mutation,match",
    [
        (
            lambda x: x["source_full_ids"].__setitem__("source_rgb", "/different"),
            "bound source",
        ),
        (lambda x: x["operations"][1].__setitem__("offset", [0, 0]), "geometry"),
        (lambda x: x["operations"][0].__setitem__("status", "skipped"), "geometry"),
        (
            lambda x: x["execution"]["versions"].__setitem__("torch", "wrong"),
            "backend/profile",
        ),
        (lambda x: x["output_shapes"].__setitem__("rgb", [1, 2, 3]), "shape"),
        (lambda x: x["input_digests"].pop("depth"), "every field"),
    ],
)
def test_execution_graph_refusals(vector, mutation, match):
    value = deepcopy(vector["execution"])
    mutation(value)
    with pytest.raises(ValueError, match=match):
        validate_execution(value, vector["descriptor"])


def test_version_negotiation_and_head_identity(vector):
    with pytest.raises(ValueError):
        TransformsAddon(vector["addon"])
    register_descriptor_validators()
    head = next(x.head for x in golden_heads() if x.name == "rgb-minimal")
    head["dataset"]["id"] = "derived_rgb"
    head["addons"] = {"euler_transforms": vector["addon"]}
    parse_dataset_head(head)
    head["dataset"]["id"] = "source_rgb"
    with pytest.raises(ValueError, match="identity"):
        parse_dataset_head(head)
    for version in ("1.1", "2.1", "3.0"):
        value = deepcopy(vector["addon"])
        value["version"] = version
        with pytest.raises(ValueError):
            MaterializedTransforms(value)
    value = deepcopy(vector["addon"])
    value["required_features"] = ["unsupported"]
    with pytest.raises(ValueError, match="features"):
        MaterializedTransforms(value)


def test_metadata_only_is_not_strict_materialization(vector):
    value = deepcopy(vector["receipt"])
    value["execution"]["verification"] = "metadata"
    with pytest.raises(ValueError, match="content-verified"):
        validate_artifact_receipt(value, vector["plan"])


def test_contradictory_output_profiles_and_revision_fail(vector):
    plan = deepcopy(vector["plan"])
    variant = next(iter(plan["profiles"]))
    plan["profiles"][variant]["storage"]["shape"][0] = 1
    with pytest.raises(ValueError, match="storage and decoded"):
        OutputPlan(plan)
    register_descriptor_validators()
    head = next(x.head for x in golden_heads() if x.name == "rgb-minimal")
    head["dataset"]["id"] = "derived_rgb"
    head["dataset"]["attributes"] = {"revision": "conflict"}
    head["addons"] = {"euler_transforms": vector["addon"]}
    with pytest.raises(ValueError, match="revision"):
        parse_dataset_head(head)
