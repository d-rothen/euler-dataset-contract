"""Head/attribute preservation through real ds-crawler storage operations."""

from __future__ import annotations

import copy
import zipfile
from contextlib import nullcontext

import pytest
from ds_crawler import (
    DatasetWriter,
    ZipDatasetWriter,
    copy_dataset,
    create_dataset_splits,
    index_dataset_from_path,
    load_dataset_split,
)
from ds_crawler.zip_utils import read_metadata_json

from euler_dataset_contract.testing import golden_head_params

from ._support import evidence, file_entries, golden


def _write(writer, full_id, basename, payload, attributes):
    if isinstance(writer, ZipDatasetWriter):
        writer.write(full_id, basename, payload, attributes=attributes)
    else:
        writer.get_path(full_id, basename, attributes=attributes).write_bytes(payload)


@pytest.mark.parametrize("case", golden_head_params())
@pytest.mark.parametrize("zip_output", [False, True], ids=["directory", "zip"])
@pytest.mark.parametrize("scope", [None, "rgb"], ids=["unscoped", "scoped"])
def test_all_golden_heads_survive_storage(tmp_path, case, zip_output, scope):
    target = tmp_path / ("dataset.zip" if zip_output else "dataset")
    head = copy.deepcopy(case.canonical)
    before = copy.deepcopy(head)
    # ds-crawler only stores bytes: these are deliberately not decoder fixtures.
    extensions = head["modality"].get("meta", {}).get("file_types", ["bin"])
    writer_class = ZipDatasetWriter if zip_output else DatasetWriter
    writer = writer_class(target, head=head, metadata_scope=scope)
    with writer if zip_output else nullcontext(writer):
        for i, extension in enumerate(extensions):
            _write(
                writer,
                f"/scene:scene_01/frame_{i}",
                f"frame_{i}.{extension}",
                b"opaque",
                {"phase0": {"unchanged": True}},
            )
        writer.save_index()
    expected = copy.deepcopy(before)
    expected["modality"].setdefault("meta", {}).setdefault("file_types", extensions)
    assert (
        read_metadata_json(target, "dataset-head.json", metadata_scope=scope)
        == expected
    )
    index = index_dataset_from_path(target, metadata_scope=scope)
    assert index["head"] == expected
    assert file_entries(index)[0]["attributes"] == {"phase0": {"unchanged": True}}
    artifact = read_metadata_json(target, "index.json", metadata_scope=scope)
    assert "head" not in artifact
    config = read_metadata_json(target, "ds-crawler.json", metadata_scope=scope)
    assert config["head_file"] == "dataset-head.json"
    assert index["head_file"] == config["head_file"]
    assert head == before


@pytest.mark.parametrize(
    "zip_source", [False, True], ids=["directory-source", "zip-source"]
)
@pytest.mark.parametrize(
    "zip_target", [False, True], ids=["directory-target", "zip-target"]
)
@pytest.mark.parametrize("scope", [None, "rgb"], ids=["unscoped", "scoped"])
def test_variants_copy_relocate_and_split_with_origin_attributes(
    tmp_path, zip_source, zip_target, scope
):
    data = evidence("source-backed")
    source = tmp_path / ("source.zip" if zip_source else "source")
    target = tmp_path / ("relocated.zip" if zip_target else "relocated")
    writer_class = ZipDatasetWriter if zip_source else DatasetWriter
    writer = writer_class(source, head=golden(data["head_case"]), metadata_scope=scope)
    with writer if zip_source else nullcontext(writer):
        for entry in data["variants"]:
            _write(
                writer,
                entry["full_id"],
                entry["basename"],
                entry["basename"].encode(),
                entry["attributes"],
            )
        writer.save_index()
    original = index_dataset_from_path(source, metadata_scope=scope)
    # Move a scoped dataset to another scope to expose accidental absolute refs.
    target_scope = "derived" if scope else None
    result = copy_dataset(
        source, target, input_metadata_scope=scope, output_metadata_scope=target_scope
    )
    assert result["copied"] == 2 and result["missing"] == 0
    copied = index_dataset_from_path(target, metadata_scope=target_scope)
    assert copied["head"] == original["head"]
    assert copied["index"] == original["index"]
    expected = {entry["basename"]: entry for entry in data["variants"]}
    for entry in file_entries(copied):
        basename = entry["path"].split("/")[-1]
        assert entry["attributes"] == expected[basename]["attributes"]
        if zip_target:
            with zipfile.ZipFile(target) as archive:
                payload = archive.read(entry["path"])
        else:
            payload = (target / entry["path"]).read_bytes()
        assert payload == basename.encode()
    split = create_dataset_splits(
        target, ["train", "test"], [0.5, 0.5], seed=0, metadata_scope=target_scope
    )
    assert split["total_ids"] == 2
    entries = []
    for name in ("train", "test"):
        hydrated = load_dataset_split(target, name, metadata_scope=target_scope)
        assert hydrated["head"] == copied["head"]
        entries.extend(file_entries(hydrated))
    assert sorted(entries, key=lambda e: e["path"]) == sorted(
        file_entries(copied), key=lambda e: e["path"]
    )
