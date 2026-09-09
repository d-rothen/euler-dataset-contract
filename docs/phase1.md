# Phase 1: descriptors, bindings, and compatibility

Implemented in the contract 0.4.0 and loading 2.23.0 source changes. No release
or publication is implied. Install the two changes together for the new APIs.
The core head format remains **Contract 1.0**, including required token-valued
`modality.key`. Its existing schemas, defaults, and acceptance rules are unchanged.

Phase 1 describes and resolves computation. `euler_transforms` 1.0 accepts only
`state: "planned"`. Neither a descriptor, successful execution, a digest, nor
an inferred profile asserts that output bytes were written. Per-sample receipts,
materialized output metadata, hierarchy-aware calibration writing, producer CLI
wiring, and evaluator GT replay remain Phase 2/3 work. The unchanged behavior
and known failures in [Phase 0 evidence](phase0-evidence.md) remain covered.

## Registry lookups

`lookup_modality(identity)` and `lookup_alias(legacy_key)` return detached records
from the shipped inventory, or `None`. `resolve_modality(key,
representation=..., declared_id=...)` returns an immutable `ModalityResolution`
with the exact `legacy_key`, resolved `modality_id`, `candidate_id`, `status`,
and actionable diagnostics. Lookup never edits a head or registers metadata rules.

```python
from euler_dataset_contract import resolve_modality

resolve_modality("sparse_depth").status                  # "conditional"
resolve_modality("sparse_depth", representation={"form": "point_cloud"}).modality_id
# "geometry.scene.points"
resolve_modality("map_3d").status                        # "provisional"
resolve_modality("spectral_map").status                  # "unused"
resolve_modality("calibration").status                   # "non_modality"
```

`spherical_map` requires `form=ray_map`; its name supplies no unit-vector
guarantee. `points_3d` denotes an organized point map, and a conflicting cloud
declaration is diagnosed. Both atmospheric-light spellings retain their exact
keys. Unknown aliases stay unresolved even when given a proposed identity;
known aliases cannot be overridden by a conflicting `declared_id`. Provisional
identities are returned with their caveat. No lookup supplies units, axes,
camera frames, a decoder, or evidence of actual dataset contents.

## Wire records and Python models

The checked-in [five-field addon](../fixtures/descriptors/five-field.json) and
[complete legacy-compatible head](../fixtures/heads/valid/phase1-planned-five-field.json)
are valid, reproducibly generated examples with real computed digests. Their
sources are explicitly **synthetic metadata-only declarations**, not audited
dataset files. `scripts/generate_phase1_fixture.py --check` checks their hashes.

All public models below are immutable mappings. They accept `from_mapping()`
and `from_json()`, return detached `to_dict()` data, and emit canonical JSON
with `to_json()`. Nested typed accessors include `TransformsAddon.recipe`,
`.sources`, `TransformRecipe.fields`, `.operations`, `FieldBinding.profile`,
and `RepresentationAddon.decoded`. The contract imports no array libraries.

| Model / record | Required meaning |
|---|---|
| `RepresentationAddon` | `version`, `modality_id`, `decoded`; optional `storage: {encoding, profile}`. Neither identity nor encoding selects executable code. Known geometric identities constrain decoded kind. |
| `RepresentationProfile` | `kind`, `layout`, ordered `shape`, canonical `dtype`, `unit`, and `invalid: {non_finite, sentinel}`. Spatial fields require `image_plane`. Depth requires `depth_kind` and `frame`; masks require `meaning`; ray/point maps require components and frame; rays require normalization. |
| `ImagePlane` | Concrete `[height,width]`, frame identity, camera model. Matching dimensions never establish correspondence. |
| `SourceBinding` | Dataset ID, exact modality key, metadata scope (`"."` means root), revision, head/index digests, decoder ID/version/profile digest, and verification level. Optional locator is access information. |
| `CalibrationBinding` | Qualified `full_id`, revision, image plane, frame, camera model, and explicit `applies_to` field names. |
| `FieldBinding` | Source alias, input profile, field policy, optional calibration, optional `selection` dictionary lookup key. Selection is access information within a sample, while calibration `full_id` is its identity. Neither is inferred from the other. |
| `ExecutionProfile` | Explicit CPU backend, exact dependency versions including build suffixes, device, work/output dtype rules, boundary handling, nearest convention, antialiasing, integer rounding, vector epsilon, numeric tolerance. |
| `OperationDescriptor` | Unique local `id`, namespaced `op`, exact semantic `version`, and parameters. |
| `TransformRecipe` | Version, reference field, one shared image plane, frozen fields, execution profile, ordered operations. |
| `TransformsAddon` | Version, planned state, sources, recipe, recipe digest. |

Layouts are `HW`, `CHW`, `HWC`, `NHW`, `NCHW`, `NHWC`, `matrix` (row/column),
or `NC` (point/column). Profile dimensions may be positive integers or symbolic
tokens; loading's first executor requires concrete dimensions. A profile can
describe point clouds and extrinsics even though resize/crop cannot transform
them as images. Unsupported fields never silently become passthrough operations.

`unit` is an explicit nonempty identifier, not a unit-conversion request.
`invalid.non_finite` says whether such values are permitted; `sentinel: null`
means no finite sentinel is declared. Units, depth kind, frame conventions,
mask meaning, and correspondence are author declarations. A sampled array
checks observable shape/dtype/value constraints, not the truth of those physical
declarations. Frame identifiers must resolve to conventions in the owning
dataset/decoder documentation; Phase 1 performs no implicit frame conversion.

Sources have `verification` equal to `metadata`, `content` (requiring
`content_digest`), or `immutable_snapshot` (requiring a snapshot identifier).
The caller must verify those assertions. Head/index identity alone cannot
detect overwritten data bytes. A decoder profile digest hashes the normalized
decoded profile using `canonical_digest()`. No decoder discovery is introduced.

## Validation and compatibility

`build_descriptor_schema(name)` returns detached Draft 2020-12 schemas for
`euler_representation`, `euler_transforms`, `recipe`, `profile`, `field`, `source`,
`calibration`, `image_plane`, `operation`, and `execution`. The four main schemas
ship under `schemas/` in the sdist and `euler_dataset_contract/_schemas/` in
the wheel. `validate_descriptor_shape(name, data)` implements the same structural
definitions without a JSON Schema runtime dependency.

Structural validation checks closed fields, types, exact known operation/addon
versions, policies, and conditional requirements. Models additionally check
foreign keys, plane/frame/shape agreement, calibration applicability and
ambiguity, bounds, unique operation IDs, profile digests, and the recipe digest.
JSON Schema cannot generally express these foreign-key/computed-digest checks;
the shared rejection corpus explicitly labels structurally valid graph failures.
Executor support is a further check in loading: describing a fisheye model or
ray regeneration does not mean this executor implements it.

Core parsing preserves unknown versioned envelopes. Register the semantic
validators explicitly with `register_descriptor_validators()` to opt a contract
reader in; importing the contract package does not register them. Loading imports
these validators in `_dataset_contract` in every process and initializes them
again when binding/resolving plans. Registration is idempotent and refuses a
conflicting registration rather than overwriting someone else's validator.

Addon, recipe, and operation versions are **exact strings**: only `1.0` is
supported here, with no automatic minor/patch fallback. Thus `1.1` and `1.0.1`
are unsupported, even if syntactically valid core addon envelopes. Numerical
changes or changed defaults need a new semantic operation version or an explicit
parameter, independently of package releases.

Addons and recipes have `required_features`, defaulting to `[]`. Known features
are `spatial.resize_crop`, `bindings.qualified`, and `profiles.decoded`. Unknown
features are structurally valid data but capable readers reject them. Required
feature arrays preserve order. There is no optional feature that permits an
unknown operation to be ignored. Old readers preserve these declarations but
cannot enforce their semantics; production materialization/replay still needs
the later, tested reader/writer integration.

## Canonical JSON and identity

`euler_dataset_contract.canonical` exports `canonical_json`, `canonical_digest`,
and duplicate-detecting `parse_json`. The encoding identifier is `euler-json-1`:

1. Encode UTF-8 with no BOM or whitespace. Sort object keys by Unicode scalar
   value; preserve all array orders. Strings retain their code points without
   NFC/NFD normalization. Escape quote/backslash, use `\b`, `\t`, `\n`, `\f`,
   `\r`, and lowercase `\u00xx` for remaining U+0000–001F. Leave other scalar
   characters, including `/`, unescaped. Reject lone surrogates.
2. Integers must be in `[-(2**53-1), 2**53-1]`. Interpret fractional JSON numbers
   as binary64. Emit their **exact decimal expansion**, with no exponent and
   no redundant trailing fractional zeros. Integral floats normalize to the
   same integer spelling; negative zero becomes `0`. For example binary64
   `0.1` emits `0.1000000000000000055511151231257827021181583404541015625`.
   Integral numbers outside the safe integer range are rejected, including floats.
3. Reject NaN/infinities, duplicate JSON keys, non-string object keys, tuples,
   sets, and other non-JSON Python values. JSON literals use lowercase spelling.
4. `canonical_digest(value)` is `sha256:` followed by lowercase hexadecimal
   SHA-256 of these bytes. This primitive excludes nothing.

This deliberately simple, exact-decimal encoding is not RFC 8785/JCS. Independent
readers must implement these rules, not hash their default JSON serializer.
The [shared vectors](../fixtures/descriptors/canonical-vectors.json) include
object/array order, numeric equivalence, control characters, and distinct Unicode
normalizations. Python's duplicate-detecting parser is the wire entry point;
once another parser has discarded duplicate keys, a mapping cannot recover them.

`recipe_digest()` first validates and expands every versioned default, removes
only recipe-level `diagnostics`, and hashes:

```python
{"canonical": "euler-json-1", "kind": "recipe", "recipe": normalized_recipe}
```

Loading expands shorthand in resize-then-crop order before this call. Resize
defaults to `pixel_centers: "half_pixel"`; crop defaults to `anchor: "center"`.
An explicit offset replaces the anchor (supplying both is rejected). Field policy
defaults are bilinear, `legacy_blend`, `preserve` rays, threshold 0.5; masks must
explicitly specify nearest. Loading expands its FieldSpec defaults, including
ray normalization, and requires consistency with supplied field policies.
Execution defaults expand CPU device, float32 spatial working dtype, preserved
output dtype, and edge boundary behavior. Pinhole matrix arithmetic uses its
declared input floating dtype; geometric ratios are binary64 before that cast.

Recipe identity covers declared profiles, source aliases, calibration selection,
operation order, and execution policy. It is distinct from source content and
does not hash source revision records outside the recipe. Calibration revision
and qualified binding inside a recipe do affect its identity.

`bound_derivation_digest(addon, source_full_ids, strict=False)` hashes an
`euler-json-1` / `bound_derivation` wrapper containing recipe digest, all source
records, addon required features, and the exact qualified source IDs. It removes
only each source's `locator` and `diagnostics`; addon/recipe diagnostics are not
included. All other source fields, including decoder/profile revisions and
content/snapshot declarations, affect identity. Every alias must have one full
ID, and calibration IDs must agree with their bindings. Full IDs start with `/`,
with no empty, `.` or `..` components. No path normalization is performed.

`strict=True` requires content or immutable-snapshot verification declarations;
it does not perform IO or independently verify those declarations. The digest
identifies a **declared bound computation**, not execution, output content, or
encoded bytes. Resolved geometry is deterministic from the hashed input plane
and operations. Encoding, output-to-source receipts, and artifact checksums will
be separate Phase 2 identities.

## Loading export and resolution

This example uses the shipped synthetic declarations; real callers must supply
their own source/profile/plane bindings. It needs no sample to resolve concrete
profiles and an explicit calibration selection:

```python
from euler_dataset_contract.testing import descriptor_fixture, evidence_cases
from euler_loading import SamplePreprocessor, execution_profile, resolve_transform_descriptor

fixture = descriptor_fixture("five-field")["addon"]
example = next(c.payload for c in evidence_cases() if c.name == "documented-five-field")
preprocessor = SamplePreprocessor.from_config(example["config"])
descriptor = preprocessor.export_descriptor(
    sources=fixture["sources"], fields=fixture["recipe"]["fields"],
    image_planes=fixture["recipe"]["image_planes"],
    execution=execution_profile("torch_cpu"),
)
plan = resolve_transform_descriptor(descriptor.to_json())
assert plan.operations[1].offset == (32, 64)
assert plan.infer_output_profiles()["rgb"].shape == (320, 640, 3)
# plan.bind_inputs(sample) validates all inputs; plan(sample) executes a detached view.
```

`SerializableTransform` defines the callable plus export boundary.
`ResolvedTransform` also exposes `bind_inputs`, ordered `operations`, composed
`image_transform`, `infer_output_profiles`, and `infer_output_bindings`.
Output bindings use a new derived plane and describe virtual calibration views,
retaining the qualified input calibration. They never rename a source matrix
as a materialized output calibration. Cached arrays and crop views cannot be
mutated through the result to change source values.

The output-plane identifier hashes the recipe digest and source bindings with
source locators/diagnostics removed, under `kind: "planned_image_plane"`. It
identifies a declared plane within that plan; it does not establish per-sample
correspondence between independent datasets.

Export rejects missing configured/inferred fields, mismatched declared kinds
or layouts, unknown operations/callable effects, fractional or boolean sizes
silently coerced by legacy config parsing, conflicting shorthand, bad crop
bounds, and ambiguous reference/calibration choices. One spatial field can
supply the reference automatically; several fields need an explicit reference.
`reduce="first"` can freeze a single keyed calibration from a representative
sample, or use an explicit selection; several candidates without a selection
fail. A source matrix's shape never establishes its camera applicability.

`MultiModalDataset.export_transform_plan(**bindings)` checks the entire current
sample chain (one preprocessor/resolved plan), registered built-in decoder
identity, declared dataset IDs/scopes, and canonical head/index-tree digests.
Its source head digest is `canonical_digest(head.to_mapping())`; its index digest
is `canonical_digest(index_tree)`, including file membership/attributes, excluding
hydrated wrapper fields. It refuses inherited calibration that varies across
the dataset; export individual bound plans for that case. Standalone preprocessor
export trusts the caller's input boundary declarations. Opaque upstream effects
must be supplied and are rejected, never treated as identity.

## First executor's numerical policies

Both backends are CPU-only, pinned to exact NumPy and Torch/Pillow versions.
`torch_cpu` accepts NumPy and CPU tensors; `pillow_cpu` accepts NumPy even if
Torch is installed. Unsupported versions, CUDA/autograd tensors, integer
geometric arrays, int32/int64 values through float32 interpolation, symbolic
dimensions, non-pinhole K, ray regeneration, and other policy combinations
are rejected before execution. Legacy callables retain their old dispatch.

| Policy | `torch_cpu` | `pillow_cpu` |
|---|---|---|
| Bilinear sampling | half pixel, align_corners=False, antialias=False | Pillow float-plane bilinear, antialiasing enabled |
| Nearest | floor convention | Pillow half-pixel convention |
| Working spatial dtype / output | float32 / preserve input | float32 / preserve input |
| Integer conversion | ties to even | named legacy cast-before-round truncation |
| Ray epsilon | 1e-12 | 1e-8 |
| Published comparison tolerance | atol=rtol=1e-5 | atol=rtol=1e-5 |

Tolerance describes numerical comparison on the tested operation profile;
it promises neither backend equivalence nor byte-identical encoded artifacts.
Masks/class values use nearest. Boolean output applies `value > mask_threshold`.
Bilinear kernels extend edge values; no padding, clipping, or value-unit change
is performed. Crop uses integer bounds, exclusive bottom/right, and floor
division for odd center offsets. Same-size resize is an identity, including for
ray magnitude, matching the existing preprocessor's conditional resize behavior.

Depth's `legacy_blend` interpolates invalid zeros ordinarily. Opt-in
`validity_aware` interpolates finite non-sentinel values and support separately,
divides where support is positive, and restores the declared finite sentinel
where support is absent. This does not make a separately resized validity mask
a statement about all interpolation support. Unit and planar/radial meaning
remain unchanged.

Rays either preserve interpolated components or use `resample_normalize` with
the pinned epsilon. This is approximate resampling, not ray regeneration from
the transformed camera model. Zero/tiny vectors do not justify a universal
unit-vector guarantee, so resized output profiles conservatively set
`normalization: "none"`; the exact normalization operation remains in the recipe.

For pinhole K, resize/crop applies `K_out = C @ R @ K_in`, scaling skew. The
documented case gives `[640,0,319.5; 0,640,159.5; 0,0,1]` and a `[32,64]` crop.
The new path tests projected points, odd/off-center crops, nonuniform scaling,
and nonzero skew. The legacy helper's skew defect remains explicitly covered
by the Phase 0 strict expected failure rather than silently changing old output.

## Verification

See the [recorded Phase 1 verification results](phase1-verification.md) for counts,
environment, distribution checks, and original-reader preservation evidence.

The corpus includes the five-field descriptor, normalized hash vectors, shared
structural/graph rejections, and a full compatible head. Core/schema tests run
without NumPy/Torch. Loading tests execute the five-field values and spawned
workers; the old consumer matrix still checks crawler, loading, preprocess,
and eval separately. Synthetic CPU fixtures do not establish CUDA parity,
actual dataset correctness, receipt capture, or materialized output metadata.

For isolated consumer worktrees, use the matrix driver's repeatable override:

```bash
uv run python scripts/check_ecosystem.py --repositories /path/to/checkouts \
  --repository euler-loading=/path/to/loading-worktree \
  --python /path/to/consumer-python --report /tmp/phase1-results.json
```
