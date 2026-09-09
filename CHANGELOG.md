# Changelog

All notable changes to this project are documented here. Package releases use
semantic versioning independently of the serialized dataset contract version.

## [Unreleased]

Phase 0 of the [ecosystem streamlining plan](docs/ecosystem-streamlining-plan.md):
inventory and fixtures. Nothing user-visible changes. No default, validation
rule, or generated schema is different, and every existing dataset head parses,
validates, and serializes exactly as before.

### Added

- A modality inventory shipped as package data
  (`euler_dataset_contract/data/modality-inventory-1.0.json`), recording the
  canonical identity behind every modality name the ecosystem emits, the two
  names that are not modalities, and which entries an open question still
  blocks. It is data only; no code path reads it in this release.
- A conformance fixture corpus under `fixtures/`: valid dataset heads with
  their canonical parsed form, invalid heads with the error each must produce,
  and a manifest. It is the cross-repository source of truth and is readable
  by non-Python consumers.
- `euler_dataset_contract.testing`, a pytest plugin registered through the
  `pytest11` entry point, exposing `golden_heads`, `invalid_heads`,
  `modality_inventory` and `assert_head_roundtrip`. A `testing` extra carries
  `pytest`; the core install stays dependency-free and does not import it.
- Regression tests asserting that every modality type `euler-loading` emits
  resolves to exactly one canonical identity, that the alias map is flat and
  acyclic, and that the `radial_depth` default stays `False` until Phase 1
  reconciles it with `euler-eval`.
- [Conformance fixtures](docs/conformance-fixtures.md), documenting the corpus,
  how a repository wires the plugin in, and the rule that a contract change is
  proven against the corpus in every repository before it ships.
- The operator's 14 modality names and clarification: homogeneous
  `spherical_map`, unused `spectral_map`, arbitrary-channel `map_3d`, distinct
  transmission/coefficient quantities, and the exact `athmospheric_light`
  spelling. Sparse-cloud aliases carry explicit conditions.
- An AST snapshot of 90 CPU/Torch loader declarations and a repeatable refresh
  script, kept separate from operator-reported dataset usage.
- Ten shared evidence cases for five-field preprocessing, known-value
  decoding/projection, calibration, backend differences, evaluation alignment,
  and source-backed persistence; 12 additional valid/canonical heads and two
  additional rejection cases.
- `EvidenceCase`, `evidence_cases()`, `evidence_case_params()`,
  `dataset_modality_types()`, and `loader_observations()` testing APIs, with
  corresponding pytest fixtures. Corpus access needs no array libraries.
- Opt-in consumer checks and `scripts/check_ecosystem.py`, with source/dependency
  provenance and strict expected failures for confirmed legacy disagreements.
  [Phase 0 evidence](docs/phase0-evidence.md) records scope and results.

### Changed

- Source and wheel distributions carry the inventory and the fixture corpus,
  and `scripts/verify_distribution.py` now fails when either is missing or when
  the pytest entry point is not registered.
- Distribution verification now follows every fixture manifest reference;
  canonical heads are checked against JSON Schema, and two existing
  runtime/schema rejection differences are explicitly recorded without
  changing either behavior.

## [0.3.0] - 2026-08-04

### Added

- Public package metadata, MIT license, contribution and security policies.
- A complete contract reference and ecosystem-informed future-directions
  document.
- Checked-in Draft 2020-12 schemas and distribution verification tooling.
- CI across all supported Python versions and a guarded trusted-publishing
  workflow.
- A `py.typed` marker for typed consumers.

### Changed

- Dataset-head JSON Schema now selects metadata requirements from
  `modality.key`, matching runtime validation.
- Core structures reject unknown keys consistently with the JSON Schema.
- Contract versions must be explicit in serialized heads.
- Boolean values are no longer accepted where numeric metadata is required.
- Modality registration validates registry keys and keeps the legacy exported
  registry view synchronized.

## [0.2.2] - 2026-07-18

- Kept evaluated type aliases importable on Python 3.9.

## [0.2.0] - 2026-03-30

- Added structured dataset-head parsing, modality metadata registration,
  addon validators, and JSON Schema generation.

[Unreleased]: https://github.com/d-rothen/euler-dataset-contract/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/d-rothen/euler-dataset-contract/compare/v0.2.0...HEAD
[0.2.2]: https://pypi.org/project/euler-dataset-contract/0.2.2/
[0.2.0]: https://github.com/d-rothen/euler-dataset-contract/releases/tag/v0.2.0
