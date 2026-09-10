# Phase 2: captured spatial exports

The Phase 2 implementation is in contract **0.5.0**, loading **2.24.0**,
crawler **2.11.0**, and preprocess **3.14.0** source trees. These versions are
unreleased. Core heads retain format `1.0` and required token `modality.key`.
The new materialized addon is **`euler_transforms` `2.0`**. The planned `1.0`
addon and its digest semantics are unchanged; it still accepts only `planned`.
This document supersedes the Phase 2 sketches in `future-directions.md`.

Generation is explicit and opt-in. This phase does not enable benchmark
production or evaluation, implement evaluator pairing, infer correspondence
from dimensions, or follow arbitrary derivation graphs. Those are Phase 3 work.

## Records and identity

The immutable Mapping models `OutputEncoding`, `OutputPlan`, `ExecutionReceipt`,
`ArtifactReceipt`, and `MaterializedTransforms` use the shared structural
validator and generated schemas. Core imports no arrays or executors. The
[wire vector](../fixtures/descriptors/phase2-five-field.json) has synthetic source
and array label hashes; it is a format vector, **not independently verified
source data**. Consumer tests use actual files made from the shared analytic
five-field corpus. `scripts/generate_phase2_fixture.py --check` verifies the vector.

| Record | Meaning |
|---|---|
| Planned `TransformsAddon` 1.0 | Frozen sources, profiles, calibration bindings, ordered recipe, recipe digest. |
| `ExecutionReceipt` 2.0 | Exact qualified source IDs, encoded source digests, input/output decoded digests and shapes, bound derivation digest, actual backend, operation order, sizes, offsets, matrices and executed/skipped status. |
| `OutputPlan` 2.0 | One output dataset ID/revision/modality/field; explicit variants and each variant's recipe, selected storage/decoded profiles, applicable calibration dependencies, encoding and original metadata scope. |
| `ArtifactReceipt` 2.0 | One output full ID and variant, output plan digest, execution, encoded artifact digest and decoded/storage profiles. |
| Materialized head | One output plan, its digest, explicit mapping mode, successful entry count and canonical index-tree digest. |

`recipe_digest` identifies computation. `bound_digest` identifies its declared
source revisions and qualified IDs. `plan_digest = canonical_digest(OutputPlan)`
adds selected output, variants, revision and encoding. Artifact SHA-256 hashes
actual encoded bytes. Receipt/reference digests hash canonical JSON using the
unchanged `euler-json-1` encoding. These identities are deliberately separate.

Each output head selects one field. `plan.dependencies[variant]` contains that
field and the calibration fields whose explicit `applies_to` names it. The
recipe/receipt can record the entire jointly executed sample; it does not claim
that all five fields are stored in each output dataset. Profiles are per variant.
Different profiles/geometry require variants declared before writing; rewriting
the recipe or adding a variant to an existing output plan is a conflict.

A small per-file `attributes.euler_transforms` has exactly one authoritative form:

```json
{"version":"2.0", "digest":"sha256:…", "receipt": {"version":"2.0", "…":"…"}}
```

Or it references a record:

```json
{"version":"2.0", "record":{"path":"records/<64 hex digits>.json", "digest":"sha256:…"}}
```

The path must match the digest. Both forms together, extra fields, missing
records, bad digests, unsupported operation/addon versions and unknown required
features fail capable validation. Execution has at most 128 operations and 64
source aliases; each execution/artifact receipt is capped at 256 KiB of canonical
UTF-8 JSON. Sidecars keep larger receipts out of indexes without removing this
per-sample bound. Output plans have at most 64 explicit variants.

Output full IDs are index hierarchy identities. Filenames and final dimensions
never establish correspondence. Output dataset ID must differ from every source
ID. The original output scope is part of its frozen logical identity; copying to
another physical metadata scope preserves that identity and resolves record paths
within the new scope. A subset receives a new membership count/digest while
preserving each selected artifact's identity and receipt.

## Verified sources and capture

`dataset.describe_transform_sources(fields, revisions=...)` computes:

* `head_digest`: canonical head mapping;
* `index_digest`: canonical indexed tree, including IDs and per-file attributes;
* `content_digest`: `canonical_digest({"kind":"source_files_1", "files":
  {qualified_full_id: "sha256:<encoded file bytes>"}})` over the entire source
  index, including files outside an eventual output subset;
* the actual allowlisted decoder identity, loading version and decoded-profile digest.

The revision name remains an author declaration. Actual indexed content is
independently read and hashed; a supplied content hash is checked against it.
Strict capture refuses metadata-only and immutable-snapshot assertions: no
immutable-snapshot verification provider is implemented. A full manifest scan
runs when capture is enabled. Per access, the selected files are checked against
that manifest and **the same bytes are decoded**. Calibration is selected by its
qualified record, ancestor applicability and explicit lookup key; multiple
sensors need an explicit selection. No cached source array or head is mutated.
Capture detaches source indexes and decoder metadata once, with direct qualified
ID lookups for replay. Each access uses that snapshot and checks the selected
bytes; it does not rehash or copy the entire source index per sample. Changing a
source path, decoder or extra modality effect requires a new capture context.

`dataset.enable_transform_capture({"variant": descriptor})` freezes the supported
sample chain. `dataset[i]` captures the first variant; `capture_sample(i,
variant_id=...)` selects another. Each returned sample has its own `provenance`.
It contains JSON data and survives spawned workers; repeated access does not
append history or depend on a mutable last-sample record. Opaque decoders,
wrappers, or extra sample/modality effects cannot disappear from the exported
chain. Standalone `execute_with_receipt` emits **metadata-only** evidence because
it cannot verify the caller's source-file hash assertions.

Strict loading writers require this source-backed capture verifier. They reject
values changed after capture and verify receipt assertions against source-backed
replay. Finalization repeats source-backed verification and encoding comparison
before publication, catching sources or outputs changed after a successful write.
This opt-in strict path favors verification over throughput: it scans sources and
can decode/replay them again at writing and finalization. Crawler alone validates
record/artifact integrity and producer assertions; it does not certify source
verification or tensor execution. A direct loading writer factory needs a
`capture=DatasetCapture(...)` verifier, not merely hashes supplied in JSON.

## Output bytes and calibration

Loading's `output_encoding()` currently supports:

| Encoding | Input / saved representation |
|---|---|
| `npy` | Exact declared NumPy array shape/dtype in C storage order; no pickles or unit conversion. |
| `png_rgb8` | HWC float32 RGB in [0,1] to uint8 codes; decoded float32 RGB. |
| `png_depth16` | HW float32 depth to uint16 codes using explicit scale (default 0.001); decoded float32 depth. |
| `png_mask8` | HW boolean mask to 0/1 uint8 codes; decoded bool. |

PNG uses ties-to-even quantization and rejects values outside the declared range;
it never silently clips. Encoding versions pin NumPy and, for PNG, Pillow.
An invalid sentinel must survive encoding exactly, and quantization must not
turn valid pixels into invalid pixels. Otherwise the PNG export is refused;
NPY preserves these values exactly.
Quantization tolerances are half a code step plus floating-point conversion
roundoff. NPY is the exact-value export for K and ray maps. GPU parity and
arbitrary codec equivalence are not claimed.

Output bytes and `attributes.output_encoding` are committed together. The latter
contains the codec, decoded profile, and encoded/decoded digests and must agree
with the receipt/head. Dataset-wide dimensions are written only when all declared
variant shapes agree; otherwise the per-file profiles/shapes are authoritative.
File types, RGB/depth range and depth scale are rebuilt from the output encoding.
Source metadata never supplies encoder parameters in this path.

`CalibrationView(descriptor, execution, field)` exposes `source`, `applies_to`,
and `cardinality="one_per_output"`. `resolve(pinned_source_K)` verifies the
source decoded digest and applies the recorded matrices, then checks the output
digest. Thus per-frame crops do not advertise one unchanged scene-wide K. K can
also be selected as its own materialized output field, addressed by output frame
IDs. Arrays remain detached from inherited source calibration.

The shared pinhole geometry now implements `K_out = C @ R @ K` for both legacy
helpers and descriptor execution. Nonuniform resize scales skew. This deliberately
fixes the old `loading-resize-skew` discrepancy; its strict xfail is now a passing
projection assertion. The two known legacy depth-scale xfails and evaluator
crop-origin xfail remain. Half-pixel centers, operation ordering and explicit
mask/depth/ray policies are unchanged.

## Publication and relocation

`ValidatedDatasetWriter.commit_bytes()` registers an entry only after bytes are
available, validated and stored successfully. It writes content-addressed artifact
paths; IDs remain independent of those paths. Repeated identical writes are
idempotent. Conflicting qualified-ID rewrites fail. Ordinary `DatasetWriter`
methods remain available for legacy files; their original lifecycle is not a
transaction guarantee.

`finalize_output()` / `ValidatedDatasetWriter.finalize()` validates expected IDs,
counts, index digest, records and artifact bytes before publication. A directory
stages canonical metadata/records under `.ds_crawler/<scope>/generations/<digest>/`
and atomically replaces `publication.json`. The pointer includes per-file digests.
Capable metadata readers resolve the selected immutable generation and reject
corruption. An interrupted finalization leaves the previous publication intact;
unreferenced staged files are not completed metadata. Directory resume requires
an identical output plan/revision and validates existing artifacts. Missing
expected outputs cannot publish a complete generation.

ZIP output has one owner and one finalization. It stages privately and replaces
the destination archive as a unit only after validation; an unfinished ZIP is
not published. Existing ZIP destinations and ZIP resume are refused. Writers are
single-owner APIs; they do not provide distributed/multi-writer coordination.
Plain filesystem output stays files-only until explicitly finalized.

`copy_dataset`, physical split operations and inline splits retain per-file
mappings and referenced records. Materialized sampling uses qualified output IDs,
including when several outputs share identical bytes. Missing/corrupt source
records fail before creating the destination publication. Scope manifests remain
available after relocation. This new publication layout requires the companion
crawler reader; older readers are not certified to discover these generations.

## Replay and use

Reloading a materialized modality uses the `materialized.data` decoder, checks
stored byte/profile digests, and **does not execute history**. Explicit
`replay_from_arrays(descriptor, execution, original_sample)` verifies decoded
array identities and reconstructs the executed view. This proves equivalence of
the supplied decoded values; it does not independently check source files.
`DatasetCapture.replay(index, provenance)` also verifies the pinned source files.
No evaluator fallback or dimension heuristic is added.

See companion loading `docs/materialization.md` and preprocess `docs/spatial.md`
for runnable API/config examples and the source installation commands in
[Phase 2 verification](phase2-verification.md).
