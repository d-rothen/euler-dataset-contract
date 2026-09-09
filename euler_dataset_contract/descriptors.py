"""Opt-in Phase 1 descriptors, reference validation, and semantic identities.

Models are immutable mappings with typed nested accessors and detached JSON
exports. Importing this module does not install validators into legacy readers.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from ._descriptor_definitions import DEFINITIONS, FULL_ID, check, normalize
from .canonical import canonical_digest, canonical_json, parse_json
from .modalities import resolve_modality

if TYPE_CHECKING:
    from .contract import DatasetHeadContract

SUPPORTED_FEATURES = frozenset(
    {"spatial.resize_crop", "bindings.qualified", "profiles.decoded"}
)
T = TypeVar("T", bound="Descriptor")


def build_descriptor_schema(name: str) -> dict[str, Any]:
    """Detached Draft 2020-12 structure; graph/digest checks require the parser.

    This schema deliberately makes no installed-executor support claim.
    Unknown required_features are valid data but rejected by capable readers.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"Euler {name} 1.0",
        **deepcopy(DEFINITIONS[name]),
    }


def validate_descriptor_shape(
    name: str, value: Any, context: str = "descriptor"
) -> None:
    """Validate JSON and shared structural rules, without loading an executor."""
    canonical_json(value)
    check(value, DEFINITIONS[name], context)


def require_features(
    value: Mapping[str, Any], *, supported: frozenset[str] = SUPPORTED_FEATURES
) -> None:
    unknown = set(value.get("required_features", [])) - supported
    if unknown:
        raise ValueError(f"Unsupported required features: {', '.join(sorted(unknown))}")


def _profile_checks(profile: dict) -> None:
    kind, layout = profile["kind"], profile["layout"]
    if kind in {"ray_map", "point_map"}:
        if "C" not in layout or profile["shape"][layout.index("C")] != len(
            profile["components"]
        ):
            raise ValueError(
                "profile: vector components must match the declared channel axis"
            )
    if kind == "point_cloud" and profile["shape"][1] != len(profile["components"]):
        raise ValueError("profile: point-cloud columns must match components")


def _recipe_checks(recipe: dict) -> None:
    require_features(recipe)
    fields, planes = recipe["fields"], recipe["image_planes"]
    reference = recipe["reference_field"]
    if reference not in fields or fields[reference]["profile"]["kind"] == "intrinsics":
        raise ValueError("recipe.reference_field must identify a spatial field")
    reference_plane = fields[reference]["profile"].get("image_plane")
    if reference_plane not in planes:
        raise ValueError("recipe.reference_field requires a declared image plane")
    if set(planes) != {reference_plane}:
        raise ValueError(
            "resize/crop recipe requires one shared, explicitly bound image plane"
        )
    plane = planes[reference_plane]
    calibration_targets: dict[str, str] = {}
    for name, binding in fields.items():
        profile = binding["profile"]
        _profile_checks(profile)
        if profile.get("image_plane") != reference_plane:
            raise ValueError(
                f"fields.{name}: image plane mismatch; matching shapes do not bind sensors"
            )
        if "frame" in profile and profile["frame"] != plane["frame"]:
            raise ValueError(f"fields.{name}: frame disagrees with image plane")
        if (
            "camera_model" in profile
            and profile["camera_model"] != plane["camera_model"]
        ):
            raise ValueError(f"fields.{name}: camera model disagrees with image plane")
        layout = profile["layout"]
        if "H" in layout and "W" in layout:
            for axis, expected in zip("HW", plane["size"]):
                actual = profile["shape"][layout.index(axis)]
                if type(actual) is int and actual != expected:
                    raise ValueError(f"fields.{name}: shape disagrees with image plane")
        elif profile["kind"] != "intrinsics":
            raise ValueError(
                f"fields.{name}: resize/crop requires spatial arrays or intrinsics"
            )
        policy = binding["policy"]
        if profile["kind"] == "mask" and policy["interpolation"] != "nearest":
            raise ValueError(
                f"fields.{name}: masks require categorical nearest resampling"
            )
        if profile["kind"] != "ray_map" and policy["rays"] != "preserve":
            raise ValueError(f"fields.{name}: ray policy applies only to ray maps")
        if profile["kind"] != "depth" and policy["invalid_depth"] != "legacy_blend":
            raise ValueError(
                f"fields.{name}: invalid-depth policy applies only to depth"
            )
        calibration = binding.get("calibration")
        if profile["kind"] == "intrinsics":
            if calibration is None:
                raise ValueError(
                    f"fields.{name}: intrinsics require a qualified calibration binding"
                )
            for key in ("image_plane", "frame", "camera_model"):
                if calibration[key] != profile[key]:
                    raise ValueError(f"fields.{name}.calibration: {key} mismatch")
            for target in calibration["applies_to"]:
                if (
                    target not in fields
                    or fields[target]["profile"]["kind"] == "intrinsics"
                ):
                    raise ValueError(
                        f"fields.{name}.calibration: invalid applicability target {target!r}"
                    )
                if target in calibration_targets:
                    raise ValueError(
                        f"fields.{name}.calibration: ambiguous calibration for {target!r}"
                    )
                calibration_targets[target] = name
        elif calibration is not None or "selection" in binding:
            raise ValueError(
                f"fields.{name}: calibration/selection is supported only for intrinsics"
            )
    ids = [operation["id"] for operation in recipe["operations"]]
    if len(set(ids)) != len(ids):
        raise ValueError("recipe.operations: duplicate operation id")
    # Bounds are data-only geometry, not a claim that the operations executed.
    size = plane["size"]
    for operation in recipe["operations"]:
        parameters = operation["parameters"]
        target = parameters["size"]
        if operation["op"] == "euler_loading.crop":
            offset = parameters.get("offset", [0, 0])
            if any(t + o > s for t, o, s in zip(target, offset, size)):
                raise ValueError(
                    f"recipe.operations.{operation['id']}: crop exceeds image plane bounds"
                )
        size = target


def _semantic_checks(name: str, value: dict) -> None:
    if name == "profile":
        _profile_checks(value)
    if name == "field":
        _profile_checks(value["profile"])
    if name in {"recipe", "euler_transforms", "euler_representation"}:
        require_features(value)
    if name == "recipe":
        _recipe_checks(value)
    if name == "euler_representation":
        _profile_checks(value["decoded"])
        if "storage" in value:
            _profile_checks(value["storage"]["profile"])
    if name == "euler_transforms":
        recipe, sources = value["recipe"], value["sources"]
        _recipe_checks(recipe)
        used = {binding["source"] for binding in recipe["fields"].values()}
        if used != set(sources):
            raise ValueError(
                "sources: every field source must resolve; unused sources are rejected"
            )
        for field, binding in recipe["fields"].items():
            source = sources[binding["source"]]
            if source["decoder"]["profile_digest"] != canonical_digest(
                binding["profile"]
            ):
                raise ValueError(f"fields.{field}: decoder profile digest mismatch")
            if (
                "calibration" in binding
                and binding["calibration"]["revision"] != source["revision"]
            ):
                raise ValueError(f"fields.{field}: calibration revision mismatch")
        if value["recipe_digest"] != recipe_digest(recipe):
            raise ValueError("recipe_digest mismatch")


@dataclass(frozen=True, init=False)
class Descriptor(Mapping[str, Any]):
    """Immutable validated JSON. Returned mappings/lists are always detached."""

    _json: str
    definition: ClassVar[str]
    __slots__ = ("_json",)

    def __init__(self, value: Mapping[str, Any]):
        if not isinstance(value, Mapping):
            raise ValueError("descriptor must be an object")
        raw = value.to_dict() if isinstance(value, Descriptor) else dict(value)
        validate_descriptor_shape(self.definition, raw)
        normalized = normalize(raw, DEFINITIONS[self.definition])
        # Canonicalization also normalizes integral float values before graph checks.
        encoded = canonical_json(normalized)
        _semantic_checks(self.definition, json.loads(encoded))
        object.__setattr__(self, "_json", encoded)

    @classmethod
    def from_mapping(cls: type[T], value: Mapping[str, Any]) -> T:
        return cls(value)

    @classmethod
    def from_json(cls: type[T], value: str) -> T:
        return cls(parse_json(value))

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._json)

    def to_json(self) -> str:
        return self._json

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def __reduce__(self) -> tuple:
        return type(self), (self.to_dict(),)


class RepresentationProfile(Descriptor):
    __slots__ = ()
    definition = "profile"

    @property
    def shape(self) -> tuple[int | str, ...]:
        return tuple(self["shape"])


class ImagePlane(Descriptor):
    __slots__ = ()
    definition = "image_plane"


class CalibrationBinding(Descriptor):
    __slots__ = ()
    definition = "calibration"


class SourceBinding(Descriptor):
    __slots__ = ()
    definition = "source"


class FieldBinding(Descriptor):
    __slots__ = ()
    definition = "field"

    @property
    def profile(self) -> RepresentationProfile:
        return RepresentationProfile(self["profile"])


class ExecutionProfile(Descriptor):
    __slots__ = ()
    definition = "execution"


class OperationDescriptor(Descriptor):
    __slots__ = ()
    definition = "operation"


class TransformRecipe(Descriptor):
    __slots__ = ()
    definition = "recipe"

    @property
    def fields(self) -> dict[str, FieldBinding]:
        return {key: FieldBinding(value) for key, value in self["fields"].items()}

    @property
    def operations(self) -> tuple[OperationDescriptor, ...]:
        return tuple(OperationDescriptor(value) for value in self["operations"])


class RepresentationAddon(Descriptor):
    __slots__ = ()
    definition = "euler_representation"

    @property
    def decoded(self) -> RepresentationProfile:
        return RepresentationProfile(self["decoded"])


class TransformsAddon(Descriptor):
    __slots__ = ()
    definition = "euler_transforms"

    @property
    def recipe(self) -> TransformRecipe:
        return TransformRecipe(self["recipe"])

    @property
    def sources(self) -> dict[str, SourceBinding]:
        return {key: SourceBinding(value) for key, value in self["sources"].items()}


def recipe_digest(recipe: Mapping[str, Any]) -> str:
    normalized = TransformRecipe(recipe).to_dict()
    normalized.pop("diagnostics", None)
    return canonical_digest(
        {"canonical": "euler-json-1", "kind": "recipe", "recipe": normalized}
    )


def bound_derivation_digest(
    descriptor: Mapping[str, Any],
    source_full_ids: Mapping[str, str],
    *,
    strict: bool = False,
) -> str:
    """Identity of declared inputs + computation, never an execution/content checksum.

    Strict mode requires declared content verification or an immutable snapshot.
    Callers are responsible for actually verifying those source assertions.
    Encoding/receipts/artifact identity will be separate Phase 2 records.
    """
    value = TransformsAddon(descriptor).to_dict()
    sources = value["sources"]
    if set(source_full_ids) != set(sources):
        raise ValueError("source_full_ids must bind every source alias exactly once")
    for alias, full_id in source_full_ids.items():
        canonical_json(full_id)
        check(full_id, FULL_ID, f"source_full_ids.{alias}")
        if strict and sources[alias]["verification"] == "metadata":
            raise ValueError(
                f"sources.{alias}: strict derivation requires content or immutable snapshot verification"
            )
        sources[alias].pop("locator", None)
        sources[alias].pop("diagnostics", None)
    for binding in value["recipe"]["fields"].values():
        if (
            "calibration" in binding
            and source_full_ids[binding["source"]] != binding["calibration"]["full_id"]
        ):
            raise ValueError(
                "source_full_ids disagrees with qualified calibration binding"
            )
    return canonical_digest(
        {
            "canonical": "euler-json-1",
            "kind": "bound_derivation",
            "recipe_digest": value["recipe_digest"],
            "sources": sources,
            "required_features": value["required_features"],
            "source_full_ids": dict(source_full_ids),
        }
    )


def validate_representation_addon(
    value: Any, context: str = "euler_representation"
) -> None:
    try:
        RepresentationAddon(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{context}: {exc}") from exc


def validate_transforms_addon(value: Any, context: str = "euler_transforms") -> None:
    try:
        TransformsAddon(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{context}: {exc}") from exc


def _validate_representation_head(head: DatasetHeadContract, context: str) -> None:
    representation = head.require_addon("euler_representation")
    resolution = resolve_modality(
        head.modality_key,
        declared_id=representation["modality_id"],
        representation={"form": representation["decoded"]["kind"]},
    )
    if resolution.status in {"conflict", "conditional"}:
        raise ValueError(
            f"{context}.addons.euler_representation: "
            + "; ".join(resolution.diagnostics)
        )


def register_descriptor_validators() -> None:
    """Explicit, idempotent process initialization; refuse conflicting validators."""
    from .validation import (
        get_registered_addon_head_validators,
        get_registered_addon_validators,
        register_addon_validator,
    )

    existing = get_registered_addon_validators()
    existing_heads = get_registered_addon_head_validators()
    registrations = (
        (
            "euler_representation",
            validate_representation_addon,
            _validate_representation_head,
        ),
        ("euler_transforms", validate_transforms_addon, None),
    )
    # Check the whole registration before mutating process state.
    for name, validator, head_validator in registrations:
        if name in existing:
            if existing[name] is not validator:
                raise ValueError(f"Conflicting addon validator for {name}")
            if name in existing_heads and existing_heads[name] is not head_validator:
                raise ValueError(f"Conflicting addon head validator for {name}")
    for name, validator, head_validator in registrations:
        if name not in existing or existing_heads.get(name) is not head_validator:
            register_addon_validator(
                name,
                validator,
                head_validator=head_validator,
                overwrite=name in existing,
            )
