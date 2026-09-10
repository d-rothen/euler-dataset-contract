"""Bound receipt and artifact contracts. No IO, arrays, or executable imports.

Validation establishes internal consistency, not independent execution evidence.
Capable producers verify content at the decoding/encoding boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._descriptor_definitions import DEFINITIONS
from ._materialization_definitions import DEFINITIONS as MATERIALIZATION_DEFINITIONS
from .canonical import canonical_digest, canonical_json
from .descriptors import (
    Descriptor,
    RepresentationProfile,
    TransformsAddon,
    bound_derivation_digest,
    require_features,
)

DEFINITIONS.update(MATERIALIZATION_DEFINITIONS)
MAX_RECEIPT_BYTES = 262144
MATERIALIZATION_FEATURES = frozenset(
    {"receipts.bound", "artifacts.sha256", "calibration.views"}
)


class OutputEncoding(Descriptor):
    definition = "output_encoding"

    def __init__(self, value):
        super().__init__(value)
        if self["range"][0] >= self["range"][1]:
            raise ValueError("encoding.range must be increasing")


class OutputPlan(Descriptor):
    definition = "output_plan"

    def __init__(self, value):
        super().__init__(value)
        OutputEncoding(self["encoding"])
        if set(self["profiles"]) != set(self["variants"]) or set(
            self["dependencies"]
        ) != set(self["variants"]):
            raise ValueError("output profiles must bind every variant")
        for variant, descriptor in self["variants"].items():
            plan = TransformsAddon(descriptor)
            if self["field"] not in plan["recipe"]["fields"]:
                raise ValueError(
                    f"variants.{variant}: selected output field is missing"
                )
            field = plan["recipe"]["fields"][self["field"]]
            dependencies = {self["field"]} | {
                name
                for name, binding in plan["recipe"]["fields"].items()
                if self["field"] in binding.get("calibration", {}).get("applies_to", [])
            }
            if set(self["dependencies"][variant]) != dependencies:
                raise ValueError(
                    "output dependencies disagree with selected field/calibration applicability"
                )
            for profile in self["profiles"][variant].values():
                RepresentationProfile(profile)
            decoded = self["profiles"][variant]["decoded"]
            storage = self["profiles"][variant]["storage"]
            if any(
                storage.get(key) != decoded.get(key)
                for key in set(decoded) | set(storage)
                if key not in {"dtype", "unit", "invalid"}
            ):
                raise ValueError(
                    "storage and decoded profiles describe different output geometry/semantics"
                )
            if self["encoding"]["id"] == "npy" and storage != decoded:
                raise ValueError("npy storage must preserve the decoded profile")
            for key in (
                "kind",
                "layout",
                "dtype",
                "unit",
                "frame",
                "camera_model",
                "depth_kind",
                "components",
                "meaning",
                "invalid",
            ):
                if decoded.get(key) != field["profile"].get(key):
                    raise ValueError(
                        "decoded output semantics disagree with selected field"
                    )
            shape = list(field["profile"]["shape"])
            size = plan["recipe"]["operations"][-1]["parameters"]["size"]
            for axis, dimension in zip("HW", size):
                if axis in decoded["layout"]:
                    shape[decoded["layout"].index(axis)] = dimension
            if decoded["shape"] != shape:
                raise ValueError("output profile shape disagrees with recipe geometry")
            if any(
                s["dataset_id"] == self["dataset_id"] for s in plan["sources"].values()
            ):
                raise ValueError("output dataset_id must be distinct from every source")


class ExecutionReceipt(Descriptor):
    definition = "execution_receipt"

    def __init__(self, value):
        super().__init__(value)
        if len(self.to_json().encode("utf-8")) > MAX_RECEIPT_BYTES:
            raise ValueError("execution receipt exceeds bounded record size")


class ArtifactReceipt(Descriptor):
    definition = "artifact_receipt"

    def __init__(self, value):
        super().__init__(value)
        ExecutionReceipt(self["execution"])
        if len(self.to_json().encode("utf-8")) > MAX_RECEIPT_BYTES:
            raise ValueError("artifact receipt exceeds bounded record size")


class MaterializedTransforms(Descriptor):
    definition = "materialized_transforms"

    def __init__(self, value):
        super().__init__(value)
        require_features(self, supported=MATERIALIZATION_FEATURES)
        if canonical_digest(OutputPlan(self["plan"]).to_dict()) != self["plan_digest"]:
            raise ValueError("materialized plan_digest mismatch")


def validate_execution(
    receipt: Mapping[str, Any], descriptor: Mapping[str, Any]
) -> ExecutionReceipt:
    """Check references and deterministic geometry without executing arrays."""
    receipt = ExecutionReceipt(receipt)
    descriptor = TransformsAddon(descriptor)
    recipe = descriptor["recipe"]
    if receipt["recipe_digest"] != descriptor["recipe_digest"]:
        raise ValueError("execution recipe_digest mismatch")
    if receipt["bound_digest"] != bound_derivation_digest(
        descriptor, receipt["source_full_ids"]
    ):
        raise ValueError("execution bound source identity mismatch")
    if set(receipt["source_content"]) != set(descriptor["sources"]):
        raise ValueError("execution source content aliases mismatch")
    if receipt["execution"] != recipe["execution"]:
        raise ValueError("execution backend/profile mismatch")
    fields = recipe["fields"]
    for key in ("input_digests", "output_digests", "input_shapes", "output_shapes"):
        if set(receipt[key]) != set(fields):
            raise ValueError(f"execution {key} must bind every field")
    if len(receipt["operations"]) != len(recipe["operations"]):
        raise ValueError("execution operation count mismatch")
    size = next(iter(recipe["image_planes"].values()))["size"]
    for configured, actual in zip(recipe["operations"], receipt["operations"]):
        target = configured["parameters"]["size"]
        resize = configured["op"] == "euler_loading.resize"
        offset = None
        if resize:
            sy, sx = target[0] / size[0], target[1] / size[1]
            matrix = [[sx, 0, (sx - 1) / 2], [0, sy, (sy - 1) / 2], [0, 0, 1]]
        else:
            params = configured["parameters"]
            if "offset" in params:
                offset = params["offset"]
            else:
                dh, dw = size[0] - target[0], size[1] - target[1]
                anchor = params["anchor"]
                offset = {
                    "center": [dh // 2, dw // 2],
                    "top_left": [0, 0],
                    "top_right": [0, dw],
                    "bottom_left": [dh, 0],
                    "bottom_right": [dh, dw],
                }[anchor]
            matrix = [[1, 0, -offset[1]], [0, 1, -offset[0]], [0, 0, 1]]
        identity = resize and size == target
        expected = dict(
            id=configured["id"],
            op=configured["op"],
            version=configured["version"],
            input_size=size,
            output_size=target,
            offset=offset,
            image_transform=matrix,
            status="skipped" if identity else "executed",
            reason="identity_size" if identity else "applied",
        )
        if canonical_json(actual) != canonical_json(expected):
            raise ValueError(
                f"execution operation {configured['id']} disagrees with resolved geometry/status"
            )
        size = target
    for name, field in fields.items():
        profile = field["profile"]
        if receipt["input_shapes"][name] != profile["shape"]:
            raise ValueError("execution input shape disagrees with profile")
        shape = list(profile["shape"])
        for axis, dimension in zip("HW", size):
            if axis in profile["layout"]:
                shape[profile["layout"].index(axis)] = dimension
        if receipt["output_shapes"][name] != shape:
            raise ValueError("execution output shape disagrees with geometry")
    return receipt


def validate_artifact_receipt(receipt, plan, *, full_id=None):
    plan = OutputPlan(plan)
    receipt = ArtifactReceipt(receipt)
    if receipt["plan_digest"] != canonical_digest(plan.to_dict()):
        raise ValueError("receipt output plan identity mismatch")
    if full_id is not None and receipt["output_full_id"] != full_id:
        raise ValueError("receipt output_full_id disagrees with index")
    variant = receipt["variant_id"]
    if variant not in plan["variants"]:
        raise ValueError("receipt variant is not declared in frozen plan")
    execution = validate_execution(receipt["execution"], plan["variants"][variant])
    if execution["verification"] != "content":
        raise ValueError("strict materialization requires content-verified execution")
    if any(
        s["verification"] != "content"
        for s in plan["variants"][variant]["sources"].values()
    ):
        raise ValueError(
            "strict materialization supports verified file content manifests only"
        )
    profiles = plan["profiles"][variant]
    if any(receipt["artifact"][key] != profiles[key] for key in ("decoded", "storage")):
        raise ValueError("artifact profiles disagree with frozen output plan")
    if (
        receipt["artifact"]["decoded"]["shape"]
        != execution["output_shapes"][plan["field"]]
    ):
        raise ValueError("artifact decoded shape mismatch")
    return receipt


def receipt_location(receipt, *, sidecar=False):
    receipt = ArtifactReceipt(receipt).to_dict()
    digest = canonical_digest(receipt)
    if sidecar:
        path = f"records/{digest[7:]}.json"
        return {"version": "2.0", "record": {"path": path, "digest": digest}}, {
            path: receipt
        }
    return {"version": "2.0", "digest": digest, "receipt": receipt}, {}


def resolve_receipt(location, read_record=None):
    """Resolve exactly one authoritative location; verify canonical JSON digest."""
    location = DescriptorLocation(location)
    if "record" in location:
        reference = location["record"]
        if reference["path"] != f"records/{reference['digest'][7:]}.json":
            raise ValueError("record path is not content-addressed by its digest")
        if read_record is None:
            raise ValueError("receipt record reader is required")
        value, digest = read_record(reference["path"]), reference["digest"]
    else:
        value, digest = location["receipt"], location["digest"]
    receipt = ArtifactReceipt(value)
    if canonical_digest(receipt.to_dict()) != digest:
        raise ValueError("receipt record digest mismatch")
    return receipt


class DescriptorLocation(Descriptor):
    definition = "receipt_location"
