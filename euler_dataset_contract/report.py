"""A versioned, JSON-ready report of the modality vocabulary this install knows.

One payload for every consumer that has to agree with this package: ds-crawler-api
serves it to euler-view, which syncs its dataset types from it, and euler-view's
cluster compatibility check reads it in a cluster environment through
``python -m euler_dataset_contract inventory``.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

from .modalities import inventory
from .schema import build_meta_schema

REPORT_KIND = "modality_vocabulary_report"
REPORT_VERSION = "1.0"
PACKAGE_NAME = "euler-dataset-contract"


def package_version() -> str | None:
    """The installed euler-dataset-contract version, if known."""
    try:
        return importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        return None


def modality_report(*, include_meta_schema: bool = True) -> dict[str, Any]:
    """The modality inventory, plus what this process registered as ``modality.meta``.

    ``modality_meta_schema`` is :func:`build_meta_schema` of the running
    process. It includes meta fields that other installed packages registered
    on import, so it describes what heads written here must carry.
    """
    report: dict[str, Any] = {
        "contract": {"kind": REPORT_KIND, "version": REPORT_VERSION},
        "package": {"name": PACKAGE_NAME, "version": package_version()},
        "inventory": inventory(),
    }
    if include_meta_schema:
        report["modality_meta_schema"] = build_meta_schema()
    return report
