"""Reject incomplete, unexpected, or unsafe release archives."""

from __future__ import annotations

import json
import stat
import sys
import tarfile
import zipfile
from collections.abc import Callable
from configparser import ConfigParser
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

SDIST_FILES = {
    ".gitignore",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "PKG-INFO",
    "README.md",
    "SECURITY.md",
    "pyproject.toml",
}
SDIST_DIRECTORIES = {
    "docs",
    "euler_dataset_contract",
    "fixtures",
    "schemas",
    "scripts",
    "tests",
}
WHEEL_PACKAGE = "euler_dataset_contract"
MODALITY_INVENTORY = "data/modality-inventory-1.0.json"
MATERIALIZATION_SCHEMAS = {
    f"{name}-2.0.schema.json"
    for name in (
        "materialized-transforms",
        "execution-receipt",
        "artifact-receipt",
        "output-plan",
    )
}
DESCRIPTOR_SCHEMAS = MATERIALIZATION_SCHEMAS | {
    f"{name}-1.0.schema.json"
    for name in (
        "euler-representation",
        "euler-transforms",
        "recipe",
        "profile",
    )
}

# Shipped data, as opposed to shipped code. A consumer that resolves modality
# identity or asserts against the conformance corpus fails at import time when
# any of these is missing, so a build that drops one must not reach PyPI.
SDIST_DATA_PATHS = {
    *(f"schemas/{name}" for name in DESCRIPTOR_SCHEMAS),
    f"{WHEEL_PACKAGE}/{MODALITY_INVENTORY}",
    "fixtures/index.json",
    "fixtures/README.md",
    "fixtures/inventory/euler-loading-modality-types.json",
}
WHEEL_DATA_PATHS = {
    *(f"{WHEEL_PACKAGE}/_schemas/{name}" for name in DESCRIPTOR_SCHEMAS),
    *(
        f"{WHEEL_PACKAGE}/{name}.py"
        for name in (
            "canonical",
            "modalities",
            "descriptors",
            "_descriptor_definitions",
            "materialization",
            "_materialization_definitions",
        )
    ),
    f"{WHEEL_PACKAGE}/{MODALITY_INVENTORY}",
    f"{WHEEL_PACKAGE}/_fixtures/index.json",
    f"{WHEEL_PACKAGE}/_fixtures/README.md",
    f"{WHEEL_PACKAGE}/_fixtures/inventory/euler-loading-modality-types.json",
    f"{WHEEL_PACKAGE}/testing/__init__.py",
    f"{WHEEL_PACKAGE}/testing/corpus.py",
    f"{WHEEL_PACKAGE}/testing/plugin.py",
    f"{WHEEL_PACKAGE}/testing/checks/__init__.py",
    f"{WHEEL_PACKAGE}/testing/checks/_support.py",
    f"{WHEEL_PACKAGE}/testing/checks/_phase2_support.py",
    *(
        f"{WHEEL_PACKAGE}/testing/checks/test_{name}.py"
        for name in ("crawler", "loading", "preprocess", "eval", "materialization")
    ),
}
PYTEST_ENTRY_POINT = "euler_dataset_contract.testing.plugin"


def _safe_parts(name: str) -> tuple[str, ...]:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe archive path: {name!r}")
    return tuple(part for part in path.parts if part not in {"", "."})


def _verify_corpus(paths: set[str], prefix: str, read: Callable[[str], bytes]) -> None:
    """Every manifest entry must survive packaging, including future cases."""
    manifest = json.loads(read(f"{prefix}/index.json"))
    referenced = []
    for entry in manifest["valid_heads"]:
        referenced.extend((entry["head"], entry["canonical"]))
    referenced.extend(entry["case"] for entry in manifest["invalid_heads"])
    for section in ("inventory", "evidence", "descriptors"):
        referenced.extend(entry["path"] for entry in manifest.get(section, []))
    for relative in referenced:
        _safe_parts(relative)
        path = f"{prefix}/{relative}"
        if path not in paths:
            raise ValueError(f"Distribution is missing manifest fixture: {path}")
        json.loads(read(path))


def _verify_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        roots = {_safe_parts(member.name)[0] for member in members}
        if len(roots) != 1:
            raise ValueError(f"Expected one source root in {path}, found {roots}")

        present: set[str] = set()
        paths: set[str] = set()
        for member in members:
            if member.issym() or member.islnk():
                raise ValueError(f"Links are not allowed in {path}: {member.name}")
            parts = _safe_parts(member.name)
            if len(parts) == 1:
                continue
            relative = parts[1:]
            present.add(relative[0])
            paths.add("/".join(relative))
            if relative[0] in SDIST_DIRECTORIES:
                continue
            if len(relative) == 1 and relative[0] in SDIST_FILES:
                continue
            raise ValueError(f"Unexpected source distribution file: {member.name}")

        missing = sorted(SDIST_FILES - present)
        if missing:
            raise ValueError(f"Source distribution is missing: {', '.join(missing)}")

        missing_data = sorted(SDIST_DATA_PATHS - paths)
        if missing_data:
            raise ValueError(
                f"Source distribution is missing shipped data: "
                f"{', '.join(missing_data)}"
            )
        root = next(iter(roots))
        _verify_corpus(
            paths, "fixtures", lambda name: archive.extractfile(f"{root}/{name}").read()
        )


def _verify_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        dist_info_dirs: set[str] = set()
        for info in archive.infolist():
            parts = _safe_parts(info.filename)
            if not parts:
                continue
            file_type = (info.external_attr >> 16) & 0o170000
            if stat.S_ISLNK(file_type):
                raise ValueError(f"Links are not allowed in {path}: {info.filename}")
            if parts[0] == WHEEL_PACKAGE:
                continue
            if parts[0].endswith(".dist-info"):
                dist_info_dirs.add(parts[0])
                continue
            raise ValueError(f"Unexpected wheel file: {info.filename}")

        if len(dist_info_dirs) != 1:
            raise ValueError(
                f"Expected one .dist-info directory in {path}, found {dist_info_dirs}"
            )
        dist_info = next(iter(dist_info_dirs))
        required = {
            f"{WHEEL_PACKAGE}/__init__.py",
            f"{WHEEL_PACKAGE}/py.typed",
            f"{dist_info}/METADATA",
            f"{dist_info}/RECORD",
            f"{dist_info}/WHEEL",
            f"{dist_info}/entry_points.txt",
            f"{dist_info}/licenses/LICENSE",
        } | WHEEL_DATA_PATHS
        missing = sorted(required - names)
        if missing:
            raise ValueError(f"Wheel is missing: {', '.join(missing)}")
        _verify_corpus(names, f"{WHEEL_PACKAGE}/_fixtures", archive.read)

        entry_points = archive.read(f"{dist_info}/entry_points.txt").decode("utf-8")
        parser = ConfigParser()
        parser.read_string(entry_points)
        registered = (
            dict(parser.items("pytest11")) if parser.has_section("pytest11") else {}
        )
        if PYTEST_ENTRY_POINT not in registered.values():
            raise ValueError(
                f"Wheel does not register {PYTEST_ENTRY_POINT!r} in the "
                f"pytest11 entry point group: {registered!r}"
            )

        metadata = BytesParser().parsebytes(archive.read(f"{dist_info}/METADATA"))
        if metadata["Name"] != "euler-dataset-contract":
            raise ValueError(f"Unexpected package name: {metadata['Name']!r}")
        if metadata["License-Expression"] != "MIT":
            raise ValueError(
                f"Unexpected license expression: {metadata['License-Expression']!r}"
            )


def main(paths: list[str]) -> None:
    if not paths:
        raise ValueError("Pass at least one .tar.gz or .whl archive")

    for raw_path in paths:
        path = Path(raw_path)
        if path.name.endswith(".tar.gz"):
            _verify_sdist(path)
        elif path.suffix == ".whl":
            _verify_wheel(path)
        else:
            raise ValueError(f"Unsupported distribution archive: {path}")
        print(f"Verified {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
