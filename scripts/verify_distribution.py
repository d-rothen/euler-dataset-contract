"""Reject incomplete, unexpected, or unsafe release archives."""

from __future__ import annotations

import stat
import sys
import tarfile
import zipfile
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
    "schemas",
    "scripts",
    "tests",
}
WHEEL_PACKAGE = "euler_dataset_contract"


def _safe_parts(name: str) -> tuple[str, ...]:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe archive path: {name!r}")
    return tuple(part for part in path.parts if part not in {"", "."})


def _verify_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        roots = {_safe_parts(member.name)[0] for member in members}
        if len(roots) != 1:
            raise ValueError(f"Expected one source root in {path}, found {roots}")

        present: set[str] = set()
        for member in members:
            if member.issym() or member.islnk():
                raise ValueError(f"Links are not allowed in {path}: {member.name}")
            parts = _safe_parts(member.name)
            if len(parts) == 1:
                continue
            relative = parts[1:]
            present.add(relative[0])
            if relative[0] in SDIST_DIRECTORIES:
                continue
            if len(relative) == 1 and relative[0] in SDIST_FILES:
                continue
            raise ValueError(f"Unexpected source distribution file: {member.name}")

        missing = sorted(SDIST_FILES - present)
        if missing:
            raise ValueError(f"Source distribution is missing: {', '.join(missing)}")


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
            f"{dist_info}/licenses/LICENSE",
        }
        missing = sorted(required - names)
        if missing:
            raise ValueError(f"Wheel is missing: {', '.join(missing)}")

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
