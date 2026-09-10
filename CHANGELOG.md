# Changelog

## 0.5.0 (unreleased)

- Add separately negotiated `euler_transforms` 2.0 materialization, bound execution
  and artifact receipts, per-output plans/variants, content-addressed references,
  shared schemas and a reproducible wire vector. Planned 1.0 behavior is unchanged.
- Add containing-head output identity/profile checks and opt-in real consumer
  capture/write/reload/replay coverage. Keep core array-free with no runtime dependencies.
- Pin the shared geometry skew correction as a passing consumer projection check.
  Evaluator pairing/alignment remains Phase 3; benchmark use remains opt-in.


All notable changes to this project are documented here. Package releases use
semantic versioning independently of the serialized dataset contract version.

## [Unreleased]

Phase 1 of the revised rollout is implemented across contract 0.4.0 and loading
2.23.0 source changes. See [the finalized wire format and APIs](docs/phase1.md).
Core Contract 1.0 schemas, required modality keys, and legacy parsing remain
unchanged. These changes have not been published.

### Phase 1 additions

- Correct the five Phase 0/1 review findings: opt-in checks against the containing
  head, exact three-segment descriptor IDs, actual built-in decoder verification,
  boolean thresholding before conversion, and exact integer crop/identity plans.
- Add optional containing-head callbacks to addon registration while preserving
  existing payload-validator signatures and readers that have not opted in.

- Detached modality/alias lookups and conditional, provisional, unused,
  non-modality, unknown, and conflict diagnostics without rewriting keys.
- Immutable representation, source, field, calibration, execution, and ordered
  operation models; opt-in `euler_representation` and planned `euler_transforms`
  1.0 validators with generated schemas from shared dependency-free definitions.
- Exact version/feature negotiation, reference and geometry integrity checks,
  canonical JSON encoding, recipe/bound-computation hashes, and shared vectors.
- Five-field descriptor, shared rejection cases, and a compatible complete head;
  schemas and the expanded fixture corpus ship in both distributions.
- Loading export/resolution protocols, explicit Torch/Pillow CPU execution,
  validity-aware depth as an opt-in policy, corrected pinhole skew in the new
  executor, output profile/virtual calibration inference, and worker registration.
- Explicit per-repository overrides in the compatibility driver for worktrees.

Receipts, materialized writer metadata, producer wiring, and GT replay remain
Phase 2/3. The Phase 0 strict expected failures and legacy behavior remain tested.

The following Phase 0 additions established that preserved baseline.

### Added

- A modality inventory shipped as package data
  (`euler_dataset_contract/data/modality-inventory-1.0.json`), recording the
  canonical identity behind every modality name the ecosystem emits, the two
  names that are not modalities, and which entries an open question still
  blocks. Phase 1 now reads this data through opt-in lookup APIs; it does not
  alter core metadata registration or decoder dispatch.
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
  acyclic, and that the `radial_depth` default stays `False`. The unchecked
  evaluator fallback remains a documented legacy caveat in Phase 1.
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
