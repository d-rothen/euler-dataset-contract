"""Structured dataset-head contract model."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable

from .registry import DATASET_CONTRACT_VERSION, DATASET_HEAD_KIND
from .validation import (
    normalize_meta_dict,
    validate_addons,
    validate_contract_kind,
    validate_contract_version,
    validate_token,
)


def _require_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _require_non_empty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


@dataclass(frozen=True)
class DatasetHeadContract:
    """Normalized dataset-head contract with namespaced addon sections."""

    contract_version: str = DATASET_CONTRACT_VERSION
    dataset_id: str = ""
    dataset_name: str = ""
    dataset_attributes: dict[str, Any] = field(default_factory=dict)
    modality_key: str = ""
    modality_meta: dict[str, Any] | None = None
    addons: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.dataset_name

    @property
    def type(self) -> str:
        return self.modality_key

    @property
    def meta(self) -> dict[str, Any] | None:
        return self.modality_meta

    @property
    def namespace_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.addons))

    @property
    def attributes(self) -> dict[str, Any]:
        return self.dataset_attributes

    def has_addon(self, name: str) -> bool:
        return name in self.addons

    def has_namespace(self, name: str) -> bool:
        return self.has_addon(name)

    def get_addon(self, name: str, default: Any = None) -> Any:
        return self.addons.get(name, default)

    def get_namespace(self, name: str, default: Any = None) -> Any:
        return self.get_addon(name, default)

    def get_addon_contract(self, name: str, default: Any = None) -> Any:
        return self.get_addon(name, default)

    def require_addon(self, name: str) -> dict[str, Any]:
        if name not in self.addons:
            raise KeyError(f"Dataset contract has no addon {name!r}")
        return self.addons[name]

    def require_namespace(self, name: str) -> dict[str, Any]:
        return self.require_addon(name)

    def to_properties_dict(self) -> dict[str, Any]:
        result = deepcopy(self.dataset_attributes)
        if self.modality_meta is not None:
            result["meta"] = deepcopy(self.modality_meta)
        for name, value in self.addons.items():
            result[name] = deepcopy(value)
        return result

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "contract": {
                "kind": DATASET_HEAD_KIND,
                "version": self.contract_version,
            },
            "dataset": {
                "id": self.dataset_id,
                "name": self.dataset_name,
            },
            "modality": {
                "key": self.modality_key,
            },
        }
        if self.dataset_attributes:
            result["dataset"]["attributes"] = deepcopy(self.dataset_attributes)
        if self.modality_meta is not None:
            result["modality"]["meta"] = deepcopy(self.modality_meta)
        if self.addons:
            result["addons"] = deepcopy(self.addons)
        return result

    @classmethod
    def from_mapping(
        cls,
        data: dict[str, Any],
        *,
        context: str = "dataset_head",
        required_addons: Iterable[str] = (),
    ) -> "DatasetHeadContract":
        if not isinstance(data, dict):
            raise ValueError(f"{context} must be an object")

        contract = _require_mapping(data.get("contract"), f"{context}.contract")
        kind = contract.get("kind")
        validate_contract_kind(kind, f"{context}.contract.kind")
        version = contract.get("version", DATASET_CONTRACT_VERSION)
        validate_contract_version(version, f"{context}.contract.version")

        dataset = _require_mapping(data.get("dataset"), f"{context}.dataset")
        dataset_id = _require_non_empty_string(dataset.get("id"), f"{context}.dataset.id")
        validate_token(dataset_id, f"{context}.dataset.id")
        dataset_name = _require_non_empty_string(
            dataset.get("name"),
            f"{context}.dataset.name",
        )
        dataset_attributes = dataset.get("attributes", {})
        if dataset_attributes is None:
            dataset_attributes = {}
        dataset_attributes = _require_mapping(
            dataset_attributes,
            f"{context}.dataset.attributes",
        )

        modality = _require_mapping(data.get("modality"), f"{context}.modality")
        modality_key = _require_non_empty_string(
            modality.get("key"),
            f"{context}.modality.key",
        )
        validate_token(modality_key, f"{context}.modality.key")
        modality_meta = normalize_meta_dict(
            modality.get("meta"),
            modality_key,
            f"{context}.modality.meta",
        )

        addons = validate_addons(data.get("addons"), f"{context}.addons")
        for addon in required_addons:
            if addon not in addons:
                raise ValueError(f"{context}.addons.{addon} is required")

        return cls(
            contract_version=version,
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            dataset_attributes=deepcopy(dataset_attributes),
            modality_key=modality_key,
            modality_meta=modality_meta,
            addons=addons,
        )
