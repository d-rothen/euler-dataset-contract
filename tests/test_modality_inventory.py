"""Assertions about the shipped modality inventory.

The inventory is data, not behaviour: nothing in the package reads it in phase
0. These tests encode the evidence in the ecosystem streamlining plan's section
2 as statements about that data, so the defects they describe cannot quietly
drift further apart while the later phases are built.
"""

from __future__ import annotations

import re

from euler_dataset_contract import build_default_meta

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2}$")
LEGACY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
STATUSES = {"settled", "provisional"}

# The modality keys this package registers meta fields for today. Hard-coded
# rather than read from the registry, because the registry is process-global and
# other tests register their own keys into it.
CONTRACT_MODALITY_KEYS = ("rgb", "depth", "segmentation", "semantic_segmentation")


def test_inventory_declares_its_contract(modality_inventory) -> None:
    assert modality_inventory["contract"] == {
        "kind": "modality_inventory",
        "version": "1.0",
    }
    assert modality_inventory["provenance"]["consumed_by_runtime"] is False


def test_every_id_matches_the_three_segment_grammar(modality_inventory) -> None:
    domains = modality_inventory["domains"]
    subjects = modality_inventory["subjects"]

    for modality_id, entry in modality_inventory["modalities"].items():
        assert ID_PATTERN.fullmatch(modality_id), modality_id
        domain, subject, quantity = modality_id.split(".")
        assert entry["domain"] == domain, modality_id
        assert entry["subject"] == subject, modality_id
        assert entry["quantity"] == quantity, modality_id
        assert domain in domains, modality_id
        assert subject in subjects, modality_id
        assert entry["description"].strip()


def test_provisional_entries_carry_a_note(modality_inventory) -> None:
    entries = list(modality_inventory["modalities"].items())
    entries += list(modality_inventory["aliases"].items())
    entries += list(modality_inventory["non_modalities"].items())

    for name, entry in entries:
        assert entry["status"] in STATUSES, name
        if entry["status"] == "provisional":
            assert entry.get("note", "").strip(), (
                f"{name} is provisional but does not say which question blocks it"
            )


def test_open_questions_name_the_entries_they_block(modality_inventory) -> None:
    known = set(modality_inventory["modalities"]) | set(modality_inventory["aliases"])
    provisional = {
        name
        for name, entry in list(modality_inventory["modalities"].items())
        + list(modality_inventory["aliases"].items())
        if entry["status"] == "provisional"
    }

    affected: set[str] = set()
    for question in modality_inventory["open_questions"]:
        assert question["summary"].strip()
        for name in question["affects"]:
            assert name in known, name
            affected.add(name)

    assert affected == provisional


# --- Section 2.4: identity, cardinality and representation are conflated ---


def test_every_emitted_modality_type_resolves_to_one_canonical_id(
    modality_inventory,
    vendored_modality_types,
) -> None:
    """Section 2.4 drift catcher.

    Every modality type euler-loading emits today is either an alias of exactly
    one canonical id or an explicitly recorded non-modality. A new type added
    upstream fails here until the inventory classifies it.
    """

    aliases = modality_inventory["aliases"]
    modalities = modality_inventory["modalities"]
    non_modalities = modality_inventory["non_modalities"]

    unresolved = []
    for modality_type in vendored_modality_types["modality_types"]:
        if modality_type in aliases:
            assert modality_type not in non_modalities, modality_type
            assert aliases[modality_type]["id"] in modalities, modality_type
        elif modality_type not in non_modalities:
            unresolved.append(modality_type)

    assert unresolved == [], (
        "euler-loading emits modality types the inventory does not classify: "
        f"{unresolved}. Add them to the inventory or record them as "
        "non-modalities."
    )


def test_non_modalities_state_why_they_are_not_modalities(
    modality_inventory,
) -> None:
    """Section 2.4: all_intrinsics is cardinality, calibration is a bundle."""

    modalities = modality_inventory["modalities"]
    reasons = modality_inventory["vocabularies"]["non_modality_reason"]
    non_modalities = modality_inventory["non_modalities"]

    assert set(non_modalities) == {"all_intrinsics", "calibration"}
    assert non_modalities["all_intrinsics"]["reason"] == "cardinality"
    assert non_modalities["calibration"]["reason"] == "bundle"

    for name, entry in non_modalities.items():
        assert entry["reason"] in reasons, name
        assert name not in modalities, name
        assert name not in modality_inventory["aliases"], name
        targets = entry.get("decomposes_to", [])
        if "resolves_to" in entry:
            targets = list(targets) + [entry["resolves_to"]]
        assert targets, name
        for target in targets:
            assert target in modalities, (name, target)


def test_extrinsics_names_share_one_identity(modality_inventory) -> None:
    """Section 2.4: extrinsics and camera_extrinsics are the same quantity."""

    aliases = modality_inventory["aliases"]
    assert aliases["extrinsics"]["id"] == aliases["camera_extrinsics"]["id"]
    assert aliases["extrinsics"]["id"] == "geometry.camera.extrinsics"


# --- The alias map itself ---


def test_alias_map_is_flat_and_acyclic(modality_inventory) -> None:
    modalities = modality_inventory["modalities"]
    aliases = modality_inventory["aliases"]

    for name, entry in aliases.items():
        assert LEGACY_NAME_PATTERN.fullmatch(name), name
        target = entry["id"]
        assert target in modalities, (name, target)
        # No alias is itself a canonical id, so resolution never has to choose.
        assert name not in modalities, name
        # An alias never points at another alias, so one lookup always ends.
        assert target not in aliases, (name, target)


def test_alias_map_and_modality_entries_agree(modality_inventory) -> None:
    modalities = modality_inventory["modalities"]
    aliases = modality_inventory["aliases"]

    from_entries = {
        alias: modality_id
        for modality_id, entry in modalities.items()
        for alias in entry["aliases"]
    }
    from_map = {alias: entry["id"] for alias, entry in aliases.items()}

    assert from_entries == from_map
    for modality_id, entry in modalities.items():
        assert entry["aliases"], modality_id
        assert len(set(entry["aliases"])) == len(entry["aliases"]), modality_id


def test_alias_sources_use_the_declared_vocabulary(modality_inventory) -> None:
    known = set(modality_inventory["vocabularies"]["alias_source"])
    for name, entry in modality_inventory["aliases"].items():
        assert entry["sources"], name
        assert set(entry["sources"]) <= known, name


def test_contract_modality_keys_are_all_covered(modality_inventory) -> None:
    aliases = modality_inventory["aliases"]
    for key in CONTRACT_MODALITY_KEYS:
        assert key in aliases, key
        assert "contract.modality_key" in aliases[key]["sources"], key


def test_representation_stays_out_of_identity(modality_inventory) -> None:
    """Section 5.2: representation is a sibling field, never an id segment."""

    modalities = modality_inventory["modalities"]
    for modality_id, entry in modalities.items():
        assert entry["representation_fields"], modality_id
        for enum_field, values in entry.get("representation_enums", {}).items():
            assert enum_field in entry["representation_fields"], modality_id
            assert len(set(values)) == len(values) > 1, modality_id

    for name, entry in modality_inventory["aliases"].items():
        declared = modalities[entry["id"]]["representation_fields"]
        for field in entry.get("representation", {}):
            assert field in declared, (name, field)


# --- Section 5.3: the three things the table settles ---


def test_sparse_depth_and_lidar_point_cloud_are_the_same_quantity(
    modality_inventory,
) -> None:
    """Section 5.3: sparsity describes a use, not an identity."""

    aliases = modality_inventory["aliases"]
    assert aliases["sparse_depth"]["id"] == aliases["lidar_point_cloud"]["id"]
    assert aliases["sparse_depth"]["id"] == "geometry.scene.points"
    # Open question 3 is unanswered, so the mapping is not yet authoritative.
    assert aliases["sparse_depth"]["status"] == "provisional"


def test_segmentation_names_resolve_to_class_labels(modality_inventory) -> None:
    """Section 2.3 and 5.3: four names, one quantity, encoding is representation."""

    aliases = modality_inventory["aliases"]
    names = (
        "segmentation",
        "semantic_segmentation",
        "class_segmentation",
        "semantic_segmentation_color",
    )
    resolved = {name: aliases[name]["id"] for name in names}

    assert set(resolved.values()) == {"semantics.camera.class_labels"}

    entry = modality_inventory["modalities"]["semantics.camera.class_labels"]
    assert entry["representation_enums"]["encoding"] == ["class_id", "rgb_palette"]


def test_sky_mask_generalizes_to_a_parameterized_mask(modality_inventory) -> None:
    """Section 5.3: a road or vehicle mask needs no new modality."""

    aliases = modality_inventory["aliases"]
    assert aliases["sky_mask"]["id"] == "semantics.camera.mask"
    assert aliases["sky_mask"]["representation"] == {"class": "sky"}


# --- Section 2.6: defaults disagree across the boundary ---


def test_radial_depth_default_is_pinned_to_false() -> None:
    """Section 2.6: euler-dataset-contract defaults radial_depth to False while
    euler-eval defaults it to True.

    This pins the contract's current value so the disagreement cannot be
    resolved by accident. Phase 1 reconciles the two sides and updates this
    test together with the default; changing it here alone would move the seam
    without moving euler-eval.
    """

    assert build_default_meta("depth")["radial_depth"] is False
