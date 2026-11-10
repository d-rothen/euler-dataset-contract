# Changelog

## Unreleased

- Loader evidence refreshed for euler-loading's new `scatternerf`, `cerema` and
  `acdc` modules (178 declarations), adding the `gated` modality type.
- Modality inventory: `appearance.camera.gated_intensity`, the slices a
  range-gated camera records, with the alias `gated` (euler-loading's
  `cerema` loaders and the CEREMA heads).
- Optional geometry meta fields. They are validated when a head declares them,
  so heads without them stay valid:
  - `intrinsics`: `camera_model`, `image_plane`;
  - `camera_extrinsics`, `extrinsics`, `lidar_to_gnss`, `lidar_pose`:
    `source_frame`, `target_frame`, `direction` (`target_from_source` or
    `source_from_target`);
  - `points_3d`, `point_cloud`, `lidar_point_cloud`, `sparse_depth`:
    `representation` (`point_cloud` or `point_map`), `columns`,
    `coordinate_unit`, `frame`, `axes`.

  The vocabulary is the `euler_representation` profiles' and the phase-0
  reference heads'. The corpus gains seven valid heads and four invalid cases;
  the phase-0 geometry heads no longer count as unregistered.
- `MetaFieldDefinition(required=False)` registers an optional field. A
  modality whose fields are all optional no longer requires `meta`, in the
  parser and in the generated head schema. `MODALITY_META_SCHEMAS` lists only
  required fields.
- **Fixed:** a registered field without a default reported a default after the
  registry's deep copies, because the `_MISSING` sentinel was copied into a new
  object. `build_default_meta` would have put sentinel objects into heads. No
  released field was affected, since all of them had defaults.
- The rules of the `euler_loading` head addon move here from euler-loading:
  `validate_euler_loading_addon`, the shared role checks
  `validate_addon_roles` (`used_as`, `slot`, `task`, `hierarchy_scope`,
  `applies_to`, reusable by `euler_train`), and the explicit, idempotent
  `register_euler_loading_addon_validator()`. Registration never replaces an
  existing `euler_loading` validator. Until now the rules were registered only
  when euler-loading was imported, so ds-crawler accepted heads that
  euler-loading then rejected, e.g. `hierarchy_scope` without
  `used_as: condition`. ds-crawler and euler-loading register them on import.
  The rules are unchanged; only where they live moves.
- Add the shared, optional `invalid` meta field: how pixels without a valid
  value are marked in the values the loader returns,
  `{"non_finite": boolean, "sentinel": number | null}`, the shape and meaning
  of a representation profile's `invalid` (a test keeps the two in step).
  euler-loading's preprocessor already reads `invalid.sentinel` to resize depth
  and disparity without blending invalid pixels in. The corpus covers it in
  `depth-sparse` (`sentinel: 0`) and `depth-source-grid` (NaN holes), and
  rejects `invalid-missing-non-finite`.
- Add the shared, optional boolean `sparse` meta field (default `false`): the
  raster holds measurements at only some pixels, the rest invalid, as in
  lidar-derived depth. euler-loading's preprocessor and euler-eval already
  read it to resample such maps without interpolating between samples; the
  contract now defines and validates it. The corpus gains `depth-sparse`
  (DrivingStereo-style) and the invalid `sparse-not-boolean`.
- Add the shared, optional `source_grid` meta field: how a dataset's pixel
  grid derives from the grid of the images it was computed from, as the
  source `size` and an axis-aligned `affine` `[[sx, 0, tx], [0, sy, ty]]` in
  the pixel-centre convention of `K_out = T @ K_in`. Per-sample values go in a
  file's `attributes.source_grid`, which overrides the head. The schemas, the
  conformance corpus (`depth-source-grid`, two invalid cases) and the new
  pure-Python helpers `check_source_grid`, `validate_source_grid`,
  `source_grid_from_rule` (rules `identity`, `resize`, `crop_top_left`,
  `crop_center`), `resolve_source_grid` and `source_grid_matrix` cover it.
- Refresh the vendored euler-loading evidence for the `driving_stereo` loader
  (euler-loading after 2.36.0, whose GPU `driving_stereo` annotations are
  spelled out so the snapshot can read them): 142 declarations (from 130).
- Register euler-loading's `disparity` (DrivingStereo) as
  `geometry.camera.stereo_disparity`, recorded as resolved plan question 9.
  The id names the stereo pair, since monocular depth models call relative
  inverse depth "disparity"; such outputs must not use the alias.
- Update the phase-0 evidence the euler-loading 2.36.0 and euler-eval 2.40.0
  resampling fixes move:
  - `backend-resize`: Torch's nearest resize samples pixel centres like
    Pillow, so the mask reads `[[true, true]]` on both backends; the bilinear
    filters still differ. Since euler-loading 2.37 the `torch_cpu` execution
    profile records `nearest: half_pixel` to match, and descriptors that
    recorded `floor` replay with it (`docs/phase1.md`);
  - `invalid-depth`: the 2×2 → 1×1 nearest mask takes the bottom-right pixel
    (`[[true]]`). Depth without a declared invalid policy still blends to 3;
  - `legacy-spatial-alignment`: the evaluator shrinks GT depth over valid
    pixels only (`[[6.67, 9]]`, from `[[5, 9]]`) and masks by nearest pixel
    centre, recorded as the new `observed_mask` that the eval check reads
    instead of a hard-coded `[::2, ::2]`.

- Register KITTI-CARLA's `lidar_pose` (the lidar-to-world pose along the
  trajectory) as `kinematics.platform.pose`, recorded as resolved plan
  question 8.
- Refresh the vendored euler-loading evidence for the `kitti_carla` loader: 130
  declarations (from 112), and the vocabulary gains `lidar_pose`.
- The opt-in preprocess check of `hierarchy-selection` follows euler-preprocess's
  calibration lookup (coherent-cropping): one matched file is used whatever its
  ID, and two files for one sample raise instead of yielding no intrinsics.
- `scripts/refresh_loader_observations.py` also folds arithmetic on numeric
  constants (`2**24 - 1`, `_FAR / _MAX`; large exponents and division by zero
  are refused), `len(...)` of a literal, `{**mapping}` unpacking, and an
  imported loader's `_cpu.func._modality_meta[...]`, resolved from that
  function's own declaration. The 130 extracted declarations equal the runtime
  annotations. It still never executes loader code.

- Register the ego-motion modality types euler-loading emits:
  - `gnss` → `kinematics.platform.state`;
  - `sensor_timing` → `timing.platform.acquisition`;
  - `lidar_to_gnss` → `geometry.platform.extrinsics`.

  They add the `kinematics` and `timing` domains and the `platform` subject,
  recorded as resolved plan question 7.
- Refresh the vendored euler-loading evidence. It had been stale since loader
  annotations started using constant expressions:
  - the declaration snapshot grows from 90 to 112 declarations and now
    includes Synscapes;
  - the modality vocabulary gains `gnss`, `sensor_timing` and
    `lidar_to_gnss`.
- `scripts/refresh_loader_observations.py` resolves `[value] * n`,
  `list(...)` / `tuple(...)` and `alias.NAME` constants of imported loader
  modules, still without executing loader code. Computed declarations are
  still rejected.

- Define the `skyclass` convention for `segmentation` / `semantic_segmentation`
  heads: the RGB value of a sky pixel in the stored file viewed as RGB, so a
  colour-coded map uses the sky colour and a single-channel class map uses
  `[v, v, v]` for sky label `v`. The field description in the generated
  schemas and the contract reference say so; validation is unchanged.
- `skyclass` accepts `null`, and `null` replaces `[0, 0, 0]` as its default: the
  sky is undeclared, so a loader uses its own default for the dataset. The key
  stays required. Producers that merge defaults, such as ds-crawler's
  `build_dataset_head`, wrote `[0, 0, 0]` into every segmentation head that set
  no sky, and loaders that read `skyclass` took it for a sky of label 0 or black.

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
