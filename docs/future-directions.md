# Future contract directions

This is a design lookout, not a promise that the next release will implement
every item. It records gaps observed across `euler-dataset-contract`,
`ds-crawler`, `euler-loading`, `euler-preprocess`, and `euler-eval`, then
proposes an order that can improve interoperability without invalidating
existing dataset heads.

The [Ecosystem streamlining plan](ecosystem-streamlining-plan.md) expands the
registry and decoded-profile work. This review amends that direction and adds
the missing producer-to-evaluator transformation contract in section 7. Where
the plans differ, the compatibility, execution, and rollout decisions here
take precedence. All new addon fields and APIs below are **proposals**, not
features supported by the current packages.

## Assessment of the direction

I agree with extending the existing contract package, keeping it free of array
dependencies, separating semantic identity from representation, and making
decoded values checkable. A separate `euler-registry` package is unnecessary.
An inspectable adapter plan is useful once its inputs and permitted effects
are explicit.

I would change five parts of the direction:

1. **Prove compatibility with old readers.** Contract 1.0 requires
   `modality.key` and rejects additional structural keys. Adding `modality.id`,
   or allowing `id` without `key`, is not a non-breaking 1.0 extension. Start
   with registry lookups and versioned addons; a new core shape needs an
   explicit version and reader migration.
2. **Make aliases conditional on evidence.** The current sparse-depth
   evaluator consumes point clouds, but the name `sparse_depth` can also mean
   a sparsely populated depth raster. Record the observed representation;
   do not declare all uses equivalent to `lidar_point_cloud`. A modality
   identity alone never proves representation or geometric compatibility.
3. **Bring geometry, lineage, and writing forward.** A shape/profile delta
   cannot distinguish a center crop from a resize. Calibration binding and
   executed operations are prerequisites for automatic spatial alignment,
   not a later refinement after a general normalization planner.
4. **Bound automation.** Data-only definitions describe values; they do not
   supply a decoder or executable transform. Use installed, registered
   implementations and explicit lossiness policies. Preserve legacy callable
   paths; unknown effects cannot be treated as identity operations.
5. **Match verification claims to evidence.** A decoded sample can prove shape
   and dtype, but a plausible numeric range cannot prove correct metric units
   or camera frames. Known-value decoding and projection fixtures are also
   required. Metadata validation has a cost and is not full conformance.

### Evidence from the reviewed checkouts

The review used the READMEs and loading/preprocessing/writing guides requested
in the task, then followed their implementations. Paths below are relative to
each named repository; commits identify the reviewed baseline.

| Repository / baseline | Evidence | Implication |
|---|---|---|
| `euler-dataset-contract` / `a8e452e` | `euler_dataset_contract/contract.py`, `DatasetHeadContract.from_mapping`; `schema.py`, `build_dataset_head_schema` | Core objects are closed; unknown versioned addons are preserved. Registering an addon validator does not currently add its rules to generated JSON Schema. |
| `ds-crawler` / `340c228` | `ds_crawler/writer.py`, `DatasetWriter.save_index`, `ZipDatasetWriter.save_index` | Heads and indexes have an existing persistence boundary, including metadata scopes and archives. No array executor belongs here. |
| `euler-loading` / `f3db6ff` | `euler_loading/preprocessing.py`, `SamplePreprocessor.from_config`, `__call__`, `_resize_spatial_value`, `_apply_reduction` | Ordered resize/crop already exists, but there is no replay export or execution receipt. Field/layout inference, sorted-key `reduce="first"`, and Torch-versus-Pillow dispatch affect results. |
| `euler-loading` / `f3db6ff` | `euler_loading/dataset.py`, `create_output_writer`, `write_sample`; `_writing.py`, `create_dataset_writer_from_index` | Writers mirror source metadata and accept output values independently of transforms. Merely attaching `dataset._transforms` would not prove what was written. Hierarchical fields cannot currently be written through `write_sample`. |
| `euler-loading` / `f3db6ff` | `euler_loading/_dataset_contract.py`, `_ALLOWED_KEYS` | Adding `preprocessors` inside the current `euler_loading` addon is rejected by its registered validator. |
| `euler-preprocess` / `7d79ec2` | `euler_preprocess/common/dataset.py`, `build_dataset`; `common/output.py`, `prepare_output_backend`, `SourceBackedOutputBackend` | The CLI does not yet pass a shared preprocessing config to the dataset. Source-backed outputs already carry metadata overrides and per-file attributes; these are integration points for receipts and variant mappings. |
| `euler-eval` / `7e445fb` | `euler_eval/data.py`, `classify_spatial_alignment`, `align_to_prediction`, `align_intrinsics_to_prediction`; callers in `evaluate.py` | Alignment guesses a top-left multiple-of-eight crop or resizes GT. Intrinsics are adjusted for that guess, but recorded center crops cannot be recovered from shape. |

The existing head corpus and modality inventory already cover part of Phase 0
([Conformance fixtures](conformance-fixtures.md)). Transformation and
decoded-value conformance still need their own evidence.

## Where the boundary sits today

The current division of responsibility is useful and should remain:

- `ds-crawler` creates, validates, stores, and hydrates dataset heads alongside
  indexes;
- `euler-dataset-contract` owns the common head model, core metadata fields,
  addon registry, and JSON Schema generation;
- `euler-loading` resolves an `euler_loading` addon, decodes files, matches
  modalities by ID, and applies spatial preprocessing;
- `euler-preprocess` generates derived datasets through source-backed writers,
  including outputs with several augmentation variants per source sample;
- `euler-eval` receives those values and adapts depth, RGB, masks, ray maps,
  point maps, point clouds, intrinsics, and extrinsics to metric-specific
  NumPy shapes.

The seam is between persisted semantics and decoded values. For example,
`euler-loading` documents CPU RGB as HWC and GPU RGB as CHW, while
`euler-eval` detects either layout. Depth may be HW, 1HW, HW1, or a
single-sample variant. Point clouds use `(N, C>=3)`, point maps use HWC or CHW,
and transforms rely on conventions that are partly carried in loader-specific
metadata. That is workable for built-in loaders but difficult for a new loader
or an independent consumer to verify mechanically.

## 1. Establish a canonical modality vocabulary

The ecosystem currently uses overlapping names:

- `segmentation`, `semantic_segmentation`, `class_segmentation`, and
  `semantic_segmentation_color`;
- `intrinsics`, `all_intrinsics`, `calibration`, `extrinsics`, and
  `camera_extrinsics`;
- `point_cloud`, `lidar_point_cloud`, `sparse_depth`, and `points_3d`;
- generic names such as `map_2d`, `map_3d`, `spherical_map`, and `rays`.

Some are true semantic differences, some are storage/encoding differences, and
some are aliases chosen by a loader. A registry should distinguish at least:

1. semantic modality identity;
2. representation or encoding;
3. sample dictionary key;
4. storage metadata scope;
5. experimental role (`input`, `target`, `condition`, `output`).

A hierarchical vocabulary can make relationships obvious. The companion
plan's three-part ids, such as `geometry.camera.intrinsics`, are a reasonable
registry convention; camera model, depth kind, and storage encoding remain
separate typed requirements. Dots are not allowed by the 1.0 token grammar,
and `modality` is closed. Prototype a richer identity in a representation
addon, retaining the required legacy key. For example, this is a **proposed
head fragment**, not an extension of the `modality` object:

```json
{
  "modality": {"key": "intrinsics"},
  "addons": {
    "euler_representation": {
      "version": "1.0",
      "modality_id": "geometry.camera.intrinsics"
    }
  }
}
```

Use the existing inventory to distinguish canonical names, unambiguous aliases,
conditional mappings, and unresolved cases. Publish resolution as data and
report conflicts between legacy keys and richer declarations. Preserve
persisted keys until an explicit migration; never infer a semantic change
solely from a path or sample key. Inline custom definitions stay local to a
head and cannot override registered meanings. They enable description and
validation; loading still requires a compatible decoder.

## 2. Separate storage, decoded output, and consumer requirements

The 1.0 `meta.dimensions`, `range`, and `scale_to_meters` fields mix concerns.
Preserve their documented meanings during migration: depth `range` is in
meters, and `scale_to_meters` multiplies raw values to obtain meters. Do not
reinterpret existing heads when introducing clearer profiles.

A file can store millimeters as uint16, a loader can return meters as float32,
and a consumer can require a CHW tensor. Those are three distinct contracts:

```text
stored artifact --decoder/profile--> decoded sample --adapter--> consumer view
```

A future representation block should describe both sides explicitly. A sketch,
deliberately not final syntax:

```json
{
  "storage": {
    "encoding": "png.uint16",
    "axes": ["height", "width"],
    "value_domain": {"unit": "millimeter", "min": 0, "max": 65535}
  },
  "decoded": {
    "container": "dense_array",
    "axes": ["channel", "height", "width"],
    "shape": {"channel": 1, "height": "H", "width": "W"},
    "dtype": "float32",
    "value_domain": {"unit": "meter", "min": 0, "max": 80},
    "invalid": {"non_finite": false, "sentinel": 0},
    "semantics": {"depth_kind": "planar_z"}
  }
}
```

Important rules for that design:

- axes are named, so HWC and CHW are unambiguous;
- symbolic dimensions allow variable resolution and cross-field constraints;
- dtype uses a small canonical vocabulary independent of NumPy or PyTorch;
- raw and decoded ranges cannot be confused;
- units, invalid values, normalization, and clipping behavior are explicit;
- sparse and dense representations are different profiles of a semantic
  modality, not overloaded modality names;
- a loader declares which output profile it implements, while a consumer
  declares which profiles it accepts;
- output writers declare the encoding and decoded profile of the **new**
  artifact, including quantization and clipping; copying an input profile is
  valid only when those properties remain true.

The contract should support validation at more than one cost level: metadata
only, sampled decoded values, or a full dataset scan. Runtime array validation
must be opt-in because checking every sample can be expensive. These checks
complement known-value decoder fixtures; no range check alone can establish
whether a plausible depth value is in centimeters or meters. The dependency-free
contract validates descriptors; decoding checks execute in `euler-loading` or
an explicitly installed CLI integration.

## 3. Formalize geometry and coordinate conventions

Shape alone is insufficient for geometry. Current loaders and evaluators need
assumptions such as:

- planar camera-axis depth versus radial Euclidean depth;
- metric, scale-relative, or affine-relative values;
- point component order (`x`, `y`, `z`) and units;
- camera model and distortion model;
- coordinate handedness and axis directions;
- source and target frame identifiers;
- whether an extrinsic matrix is `target_from_source` or
  `source_from_target`;
- the image plane/resolution to which intrinsics apply;
- whether crop and resize have already updated the intrinsics.

These should become typed fields with controlled values. In particular,
`geometry.camera.extrinsics` should carry `source_frame`, `target_frame`, matrix layout,
and transform direction. Intrinsics should name their camera model and image
plane. A transform should be composable without relying on dataset-specific
loader documentation. Image-plane changes and camera-frame changes are
different effects: cropping changes the principal point, not the camera pose.
Version the pixel-center, interpolation, and rounding conventions as part of
the operation semantics (section 7.5).

## 4. Make hierarchy and applicability typed

`euler-loading` already handles calibration inherited from an ancestor in the
dataset hierarchy and supports `hierarchy_scope`, `applies_to`, and
`collapse_single`. The common contract does not express enough to prove that a
given calibration applies to a particular image modality.

A future binding model could identify:

- the hierarchy levels at which a value may be defined;
- inheritance and override rules;
- the exact target modality identity or sensor frame;
- cardinality (`one`, `one per sensor`, or `many`);
- whether a consumer receives a direct value or a keyed collection.

This would remove name-based assumptions such as selecting the first or
deepest calibration entry without knowing its semantic target. Persist the
chosen calibration's qualified identity and revision in an execution receipt.
If crop boxes differ per frame, inherited source calibration may stay shared,
but the transformed intrinsics are per-frame views or separately materialized
outputs. Never mutate a shared cached calibration for one sample.

## 5. Define version negotiation and extension governance

Version strings are validated syntactically today, but compatibility behavior
is not formalized. Before a 2.0 contract, define:

- whether an older reader may accept a newer minor version;
- how required versus optional capabilities are advertised;
- how unknown core fields differ from unknown addon fields;
- how an addon declares the core contract versions it supports;
- how modality and representation registry entries are versioned;
- when an alias becomes deprecated and when it may be removed.

Runtime validation and generated JSON Schema must remain conformance-tested
against the same fixtures. Each ecosystem package should run those fixtures so
that a contract change cannot pass locally while breaking loading or
evaluation.

Ship explicit addon schemas alongside addon runtime validators; the current
addon registration hook supplies only the latter. Parser acceptance of an
unknown addon means it can be preserved, not that its semantics are supported.
Transformation-aware readers must reject unsupported required operation or
addon versions before alignment. Unchanged old evaluators cannot be made safe
by inserting a new capability flag they do not understand; production use
needs tested minimum reader versions and rollout controls.

## 6. Provide explicit conversion and validation adapters

Once representations are declared, conversion should be a named, inspectable
step rather than a collection of consumer heuristics. Examples include:

- HWC ↔ CHW;
- integer color ↔ normalized float color;
- millimeters ↔ meters;
- planar ↔ radial depth, requiring matching intrinsics;
- dense depth ↔ camera-frame point map;
- 3×4 ↔ homogeneous 4×4 transforms;
- class-color encoding ↔ class IDs.

An adapter should state preconditions, output contract, lossiness, and required
side inputs. Silent guessing is unsafe when a shape is ambiguous—for example a
3×W×3 array can look both channel-first and channel-last. Start with a bounded
set of operations and deterministic plan selection. Lossy casts, palette
conversion, resampling, and fitted transformations require the consumer's
explicit policy; satisfying a requested shape does not authorize changing the
measurement domain.

Use the same operation implementations for explicit pipelines and planned
adapters, but distinguish two planning inputs: representation adaptation uses
declared profiles; spatial alignment additionally needs sample correspondence
and executed lineage. A crop cannot be planned from a profile delta alone.
Do not reorder existing user transforms as an incidental normalization change.
An unregistered callable may continue to run locally, but its output profile
and replayability become unknown unless its author supplies a checked
descriptor.

## 7. Persist deterministic transformations from generation to evaluation

The requirement is to retain the meaning of this workflow across processes:
configure `SamplePreprocessor`, generate a dataset, save its head, then evaluate
predictions on its image plane against the original GT. The evaluator should
be able to reconstruct the relevant GT view and its intrinsics without the
producer's Python objects or an extra handwritten crop config.

```mermaid
flowchart LR
    S["Source heads, samples, calibration"] --> L["euler-loading: bind and execute"]
    L --> P["euler-preprocess or another producer"]
    P --> W["Output values and execution receipts"]
    W --> D["ds-crawler: persist artifacts"]
    D --> H["Derived head, index, transform records"]
    H --> E["euler-eval: resolve correspondence and GT view"]
    S --> E
    E --> M["Metrics on a verified common image plane"]
```

### 7.1 Ownership and where the metadata belongs

Use one versioned **`addons.euler_transforms`** extension for materialized
derivations. Keep `addons.euler_loading` for resolving the decoder/writer of
the saved bytes. The suggested `addons.euler_loading.preprocessors[]` captures
the right need, but changing that closed addon requires reader upgrades and
the name does not distinguish past execution from instructions to run again.
A separate namespace also allows non-loading producers to describe the same
operations without claiming ownership of loading configuration.

| Owner | Responsibility |
|---|---|
| `euler-dataset-contract` | Dependency-free descriptor models, the shared addon envelope, source/field references, version rules, standalone JSON Schema, and conformance data. It validates descriptions without importing executors. |
| `euler-loading` | Built-in operation definitions and implementations; recipe export/resolution; field and calibration binding; execution receipts; output-head planning; alignment planning. |
| `ds-crawler` | Persist validated heads, index attributes, and referenced records for directories, ZIPs, and scopes. Preserve references during copy/split operations. No interpretation of tensor operations. |
| `euler-preprocess` and other generators | Declare which inputs caused each output, forward receipts, describe their own value-changing operations, and identify variants. Reuse shared resize/crop implementations. |
| `euler-eval` | Choose the allowed comparison domain, ask loading for a verified alignment plan, execute the GT view, and record the plan in results. No second implementation of crop or intrinsics math. |

The head describes **one logical output modality**, not the entire multimodal
dataset. Each output head records its own selected output and dependencies.
Several heads may reference one immutable recipe bundle, but their current
profiles, sample mappings, and materialization claims remain distinct.

### 7.2 Separate recipe, execution receipt, and current artifact

A **recipe** describes an ordered computation before samples are available.
An **execution receipt** records the choices actually made for a particular
source sample and output. The **output head** describes what its saved bytes
mean now and links them to that history. All three are necessary:

| Record | Required information |
|---|---|
| Recipe | Schema version; ordered operation ids and semantic versions; expanded parameters; explicit field kinds, layouts and interpolation policies; reference image plane; required side inputs; declared effects and pre/postconditions. |
| Source binding | Local source alias; dataset id, modality key, metadata scope, immutable revision/digests; calibration/sensor binding; decoder and decoded-profile identity. A path is an optional locator, never identity. |
| Execution receipt | Output and source qualified IDs; variant id where applicable; resolved operation order, input/output sizes and crop boxes; chosen calibration identity; resolved parameters and actual backend; executed/skipped status with reason. |
| Output declaration | Selected output field; materialized state; current storage/decoded profile and image plane; actual dependencies; receipt location and recipe digest. |

For the configuration in `euler-loading/docs/preprocessing.md`, export expands
the shorthand to **resize to `[384, 768]`, then crop to `[320, 640]`**. Array
sizes use `[height, width]`; offsets use `[top, left]`. Preserve list order.
Aliases and implicit defaults are resolved before the canonical recipe is
hashed. For a center crop at that intermediate size, the receipt records
`offset: [32, 64]` even if the author configured `anchor: "center"`.

Export must include the effective bindings for all five configured fields:

| Field | Binding and behavior to persist |
|---|---|
| `rgb` | Source modality and image plane; resolved layout; image resampling policy. |
| `depth` | Source modality on the same plane; planar/radial meaning and units; interpolation and invalid-depth policy. |
| `valid_mask` | Target plane and validity meaning; nearest-neighbor convention and boolean threshold, if used. |
| `intrinsics` | Camera model, source image plane, qualified calibration identity and application targets; geometry update rule. |
| `ray_map` | Direction convention/frame; resampling-and-renormalization or regeneration policy, explicitly distinguished. |

`infer_fields=True`, automatic layout/reference-field selection, and
`reduce="first"` remain authoring conveniences. A replayable export freezes
their resolved choices. Sorted-key selection is repeatable but does not prove
that calibration belongs to the right sensor. Accept the example's reduction
when there is one applicable calibration; otherwise require an explicit
binding and reject ambiguity. Missing required fields, mismatched source
planes, and silently skipped operations cannot yield a complete replay claim.
Record conditional absence only if the operation contract explicitly allows it.

### 7.3 Proposed persisted shape and sample correspondence

This head sketch shows an RGB output and its calibration dependency. A full
five-field recipe uses the same structure for the other source bindings.
Digest strings in angle brackets are explanatory placeholders, not valid
digests; field names are proposed. The current 1.0 parser can preserve the
addon envelope, but does not validate or execute this new payload.

```json
{
  "contract": {"kind": "dataset_head", "version": "1.0"},
  "dataset": {"id": "cropped_rgb", "name": "Resized and cropped RGB"},
  "modality": {
    "key": "rgb",
    "meta": {
      "range": [0, 255],
      "dimensions": {"height": 320, "width": 640, "channels": 3},
      "file_types": ["png"]
    }
  },
  "addons": {
    "euler_loading": {"version": "1.0", "loader": "generic_dense_depth", "function": "rgb"},
    "euler_transforms": {
      "version": "1.0",
      "state": "materialized",
      "sources": {
        "source_rgb": {
          "dataset_id": "original_rgb", "modality_key": "rgb", "metadata_scope": "rgb",
          "head_digest": "sha256:<rgb-head>",
          "index_digest": "sha256:<rgb-index>",
          "content_digest": "sha256:<rgb-content-manifest>"
        },
        "source_camera": {
          "dataset_id": "original_intrinsics", "modality_key": "intrinsics", "metadata_scope": "intrinsics",
          "head_digest": "sha256:<camera-head>",
          "index_digest": "sha256:<camera-index>",
          "content_digest": "sha256:<camera-content-manifest>"
        }
      },
      "recipe": {
        "version": "1.0",
        "reference_field": "rgb",
        "fields": {
          "rgb": {"source": "source_rgb", "kind": "image", "layout": "CHW", "interpolation": "bilinear"},
          "intrinsics": {"source": "source_camera", "kind": "intrinsics", "applies_to": ["rgb"], "model": "pinhole"}
        },
        "operations": [
          {"id": "resize_1", "op": "euler_loading.resize", "version": "1.0", "parameters": {"size": [384, 768], "pixel_centers": "half_pixel", "antialias": false}},
          {"id": "crop_1", "op": "euler_loading.crop", "version": "1.0", "parameters": {"size": [320, 640], "anchor": "center"}}
        ]
      },
      "recipe_digest": "sha256:<normalized-recipe>",
      "sample_mapping": {"kind": "identity", "source": "source_rgb", "key": "full_id"},
      "output": {"field": "rgb", "image_plane": "cropped_camera", "size": [320, 640]},
      "receipts": {"storage": "file_attributes", "key": "euler_transforms"}
    }
  }
}
```

The operation version supplies normative defaults omitted in this sketch;
canonical export expands them, including numeric policies and decoder/profile
bindings. The recipe digest covers the recipe; source and execution identities
are separately included in the derivation digest used for caching (section
7.4). Output storage metadata is authoritative for decoding the saved PNG;
the historical recipe's layout describes its input values, not the PNG layout.

Keep invariant recipes in the head while small. Larger recipes and receipts
may use content-addressed, versioned JSON records referenced by relative path
and digest beneath the same `.ds_crawler` metadata scope. Scope-relative paths
resolve within the archive for ZIPs. The head carries a bounded summary and
reference; do not put millions of crop boxes into it. Recipe/receipt references
must survive packaging, scope relocation, copying, and splitting, with missing
or changed referenced bytes reported before replay. Store each record in one
authoritative location rather than conflicting inline and sidecar copies.

Small per-sample receipts fit the existing index entry's
`attributes.euler_transforms` namespace, exposed by loading under
`sample["attributes"][modality]`. For example, a variant receipt can contain:

```json
{
  "version": "1.0",
  "recipe_digest": "sha256:<normalized-recipe>",
  "output_full_id": "/scene_01/camera_0/frame_001/crop_a",
  "source_full_ids": {
    "source_rgb": "/scene_01/camera_0/frame_001",
    "source_camera": "/scene_01/camera_0/calibration"
  },
  "variant_id": "crop_a",
  "operations": [
    {"id": "resize_1", "status": "executed", "input_size": [480, 960], "output_size": [384, 768]},
    {"id": "crop_1", "status": "executed", "offset": [32, 64], "output_size": [320, 640]}
  ]
}
```

This illustrates the **explicit mapping** alternative to the head's identity
mapping; a variant-producing head must select that mode and reference its
records. Qualified IDs include hierarchy, not just a basename or leaf ID.
Datasets and scopes are identified by the source aliases in the receipt.
Preserved IDs can use the compact identity rule, but subsets still enumerate
the outputs actually written. Changed IDs and one-to-many variants require an
explicit output-to-source mapping; never recover it by splitting a filename.
Splits select/filter mappings as well as samples. Many-to-one derivations need
typed dependencies and are outside the first alignment implementation.

An RGB source and a GT depth source may have different dataset ids. Pairing
them requires a declared cross-modal correspondence and the same sensor/image
plane, or an explicit evaluator-supplied mapping. Equal leaf IDs or equal
dimensions alone are insufficient. Bind runtime keys such as `gt`, `pred`, or
`rgb` to these references at the consumer boundary; never persist those names
as a universal identity rule.

### 7.4 What deterministic means

The initial replayable operations are explicit resize and crop, with no random
sampling. A recipe is deterministic only relative to declared source values,
resolved parameters, operation semantics, and an execution profile:

- Give each operation a namespaced id and a semantic version, independent of
  the package version. Changing pixel centers, kernel behavior, or a default
  requires a new operation version or explicit parameter value. Unsupported
  versions must fail resolution; no fallback to the latest implementation.
- Specify interpolation, nearest-neighbor tie rules, antialiasing, boundary
  handling, intermediate/output dtype, integer rounding, mask thresholds,
  vector normalization epsilon, clipping, and invalid-value treatment where
  applicable. A string such as `bilinear` alone is insufficient.
- Pin the actual backend and dependency versions in the receipt. The current
  NumPy path can use Torch if installed and Pillow otherwise; export must not
  preserve that as an implicit environment-dependent choice.
- Distinguish exact discrete replay, numeric replay within a published
  operation-specific tolerance, and byte-identical artifact reproduction.
  Codec versions, compression, dtype conversion, and execution environment
  are additional requirements for the last claim. CPU/GPU equivalence needs
  fixtures; an implementation label is not a promise of bitwise equality.
- Publish a versioned canonical JSON encoding and hash test vectors before
  stabilizing the wire format. Normalize shorthand/defaults, preserve array
  order, forbid non-finite parameters, define number/string encoding, and
  exclude locators and diagnostic timestamps from semantic hashes. A recipe
  digest is not a checksum of source data.
- Pin head, index membership, calibration, decoder profile, and actual content
  revisions. A head/index digest alone cannot detect overwritten image bytes.
  Permit metadata-only provenance with an explicit weaker verification level,
  but require content verification or a verified immutable snapshot for strict
  reproduction. Do not force a full data hash at every load; verified
  manifests can be reused.

For future random crops or fog variants, a global seed is insufficient: worker
count, batching, and iteration order can change draws. Derive independent RNG
streams from stable source/variant/operation identities and a specified RNG
algorithm, and persist realized parameters. Data-dependent selections need
their resolved result and dependencies too. Such operations remain outside
deterministic replay until their receipts make execution complete.

Use a derivation/cache digest over the normalized recipe, bound source
revisions and qualified IDs, resolved parameters, calibration, operation and
backend profiles, and output encoding as relevant. Evaluation caches must
also include field mapping, comparison policy, and target plane. Equal shapes
or equal recipe configs do not make two derived samples interchangeable.

### 7.5 Geometry is part of operation conformance

Resolve one source image plane and validate that jointly transformed fields
occupy it. Independent sensor resolutions require an explicit mapping before
a shared crop can be applied. Persist every intermediate image size and use
zero-based pixel centers; crop boxes have integer `[top, left, height, width]`
with exclusive bottom/right bounds. Center crops use floor division on odd
differences. Out-of-bounds crops fail; padding would be a separate operation
with a validity mask.

For the proposed pinhole half-pixel resize, let `sx = W1/W0`, `sy = H1/H0`.
For crop offsets `top`, `left`, the image-coordinate transforms are:

```text
R = [[sx, 0, (sx - 1)/2], [0, sy, (sy - 1)/2], [0, 0, 1]]
C = [[1, 0, -left], [0, 1, -top], [0, 0, 1]]
K_out = C @ R @ K_in
```

Thus `fx' = sx*fx`, `fy' = sy*fy`,
`cx' = (cx+0.5)*sx-0.5-left`, and
`cy' = (cy+0.5)*sy-0.5-top`. Scale skew as well. The current loading helper
updates focal lengths and principal point but not skew, while eval's resize
helper does scale skew; consolidate this behavior with a nonzero-skew fixture.
The first executor should support declared pinhole matrices; other camera
models need registered rules and must not silently use this formula.

For a source of `480×960` with `fx=fy=800`, `cx=479.5`, `cy=239.5`, resizing
to `384×768` and center-cropping to `320×640` yields `fx'=fy'=640`,
`cx'=319.5`, `cy'=159.5`. A fixture should verify projected points, not only
the output matrix shape. Compose geometry matrices for validation, but retain
the ordered resampling operations: two interpolations generally cannot be
replaced with one interpolation of their composed matrix.

Apply the corresponding rules to every dependent field:

- Depth resizing changes its sampling grid, not its metric unit or
  planar/radial meaning. Explicitly select invalid-depth handling; ordinary
  bilinear interpolation can blend invalid zeros into valid depths. Preserve
  a named legacy policy when reproducing old behavior; introduce an explicit
  validity-aware policy for new datasets instead of silently changing results.
- Masks and class labels require categorical resampling. Define the validity
  support used in metrics; a resized mask alone may not describe all invalid
  contributions to an interpolated depth pixel.
- Cropped ray maps select the corresponding rays. For resize, resampling and
  renormalization is an approximation and differs from regenerating rays from
  the transformed camera model. Declare which was used and test its tolerance.
- Camera-frame/world-frame point coordinates are not scaled by image resize.
  Point maps need their own sampling policy; sparse clouds should be projected
  with the transformed intrinsics and cropped support, not resized as images.
- Crop/resize preserves camera pose and planar/radial meaning. Planar-to-radial
  conversion is a separate value operation requiring matching intrinsics/rays;
  it is not generally interchangeable with depth interpolation in the recipe.

Persist updated calibration as a separate derived modality when needed by
ordinary consumers, or expose a typed virtual calibration view from the
referenced source plus receipt to capable readers. Per-frame transformations
cannot be written back as one unchanged scene-wide calibration. Supporting
materialized calibration needs a hierarchy-aware writer API; today's
`write_sample` only addresses regular modalities. Geometry-aware export must
require a valid output binding rather than leaving a stale source binding.

### 7.6 The writing pathway

Add an opt-in serializable-transform protocol to loading: export a normalized
descriptor, validate/bind inputs, execute while returning a receipt, and
resolve a descriptor through an installed operation registry. Preserve the
existing callable interface. Loading captures the entire effective chain,
including per-modality transforms and representation adapters before
`SamplePreprocessor`; a hidden earlier transform invalidates replayability.
The executor carries receipts with the sample through workers, not in mutable
dataset-global state or a log that the writer must reconstruct.

Proposed API flow, using new arguments and methods rather than claiming they
exist today:

```python
# dataset already contains the configured SamplePreprocessor in transforms.
plan = dataset.export_transform_plan()
writer = dataset.create_output_writer(
    "rgb", "/out/cropped_rgb",
    dataset_id="cropped_rgb", derivation=plan,
)
for i in range(len(dataset)):
    sample = dataset[i]  # Proposed: includes sample["provenance"] receipts.
    dataset.write_sample(
        i, {"rgb": sample["rgb"]}, writer,
        provenance=sample["provenance"],
    )
writer.save_index()
```

The writer factory uses the plan as a declaration; **successful writes with
receipts establish materialization**. `write_sample` must validate that the
receipt names this sample, output field, source revision, recipe, and observed
output profile. Producers remain responsible for declaring additional changes
to the values they pass. A model prediction needs its own producer record and
an explicit output-plane binding; copying an RGB preprocessing receipt onto
depth predictions does not assert that the depth values are a replay of RGB.

Required lifecycle behavior:

1. Prepare a detached output head with a distinct derived dataset id/revision,
   source references, and a frozen plan. Do not mutate the source head or
   blindly inherit source transforms as instructions for new bytes.
2. Build the output storage profile and writer metadata together. Recompute
   dimensions when uniform, omit dataset-wide dimensions when variable, and
   update depth scale/range, encoding, file types, and calibration bindings as
   needed. `write_sample` currently passes source metadata to the encoder;
   the new pathway must pass the output encoding metadata instead.
3. At each successful write, persist the output-to-source mapping and receipt
   for the fields actually written. Include encoding/quantization effects in
   artifact provenance. Reject missing receipts, inconsistent revisions,
   incomplete chains, and unauthorized recipe changes within a strict writer.
4. Finalize heads, indexes, receipts, and referenced calibration together.
   Validate counts and references before publishing the artifact set. Stage
   directory metadata and replace completed ZIPs as a unit; partial writes
   must not appear as complete derivations. Define this as a new finalization
   guarantee, not an assumption about current `save_index` behavior.
5. Make resume and repeated directory finalization idempotent by output
   qualified ID plus derivation identity. Reject conflicting rewrites; never
   append the same history each time `save_index` is called. Respect the
   existing single-owner, single-finalization ZIP lifecycle.

Plain-path writes still produce files only. Durable replay requires a dataset
writer or an explicit equivalent metadata finalization path. Direct users of
`create_dataset_writer_from_index` or `ds-crawler.DatasetWriter` can pass an
explicit derivation descriptor and validated receipts; they need not create a
`MultiModalDataset` solely to author metadata.

Unknown callables can be recorded as opaque producer steps, with known sources
and outputs where supplied. They cannot be serialized via `repr`, pickles,
lambdas, or arbitrary import paths in a head. A strict replay writer refuses an
opaque step; an ordinary materialized dataset may preserve that history but
cannot advertise replay across it. Registered code is installed explicitly;
reading a head never installs packages or executes embedded code.

In `euler-preprocess`, add the shared preprocessing config to `build_dataset`
and thread receipts through `prepare_output_backend` and
`SourceBackedOutputBackend.write/finalize`. A crop command can then be a thin
wrapper over the same loading operations. Fog, sky-depth overrides, and radial
conversion supply their own operation descriptors and dependencies. Preserve
existing fog attributes and add structured source/variant mappings. Capture
stages that include crop/resize or lens distortion must expose their spatial
effects even when embedded in an otherwise photometric pipeline; RGB and
auxiliary fog maps need not share the resulting plane.

### 7.7 Resolve evaluation from lineage, not shape

Loading a materialized output **never reapplies its recorded preprocessing**.
The addon is history. Version 1 covers materialized datasets only; executable
virtual datasets would require a separately negotiated state and resolver.
Evaluation constructs a transient view of GT to match an explicitly chosen
prediction plane:

1. Read both heads, source bindings, and mapping records. Check required addon
   and operation versions before intersecting samples; variants need the
   output-to-source join, not the current direct intersection of output IDs.
2. Resolve a unique cross-modal correspondence and verified common source
   plane. Follow parent references for chained derivations, preserving ordered
   history; detect cycles, missing revisions, and ambiguous ancestry. A shared
   dataset name or matching recipe hash alone does not establish ancestry.
3. Compute only the forward spatial operations missing on the GT branch.
   If GT and prediction already share the same verified plane/history, do
   nothing even if their heads contain recipes. If GT is a prefix of the
   prediction derivation, execute the remaining steps. Do not deduplicate
   repeated operations just because their configs match: two crops may both
   have been executed intentionally.
4. Apply the plan through loading to GT, validity/semantic masks, rays, and
   the applicable intrinsics together. Bind field kinds from GT semantics;
   replay the same spatial mapping with an explicitly allowed per-field
   sampling policy, not RGB interpolation indiscriminately on every field.
   Include policy-approved semantic conversions at their required positions
   in the ordered plan; planar-to-radial conversion cannot automatically be
   moved across a depth resize.
5. Check the resulting plane, dimensions, units, calibration, and valid support
   against prediction requirements. Apply remaining compatible layout/dtype
   adapters and then the evaluator's existing `native`/`metric` scale or gauge
   fitting. Benchmark-specific crops remain separate, explicitly recorded
   evaluation policy.
6. Write source/recipe digests, realized spatial plan, calibration binding,
   sampling policy, supported pixel region/count, exclusions, and any legacy
   override into `eval.json`. Include these in cache identity so two variants
   with the same size cannot share an incorrect cached GT view.

Cropping is not invertible; resizing usually is not either. For divergent
branches, the first implementation requires the pinned original GT and replays
forward to the requested plane, or refuses. Later support may choose an
explicit common supported region. It must report coverage and cannot invent
discarded GT pixels by upsampling a crop. If prediction generation adds another
crop/resize after its inputs were prepared, that output-plane change must also
be recorded; matching input preprocessing alone is insufficient.

Separate **alignment effects** from **value-generation effects**. Do not replay
fog, noise, sky-depth replacement, or model inference onto GT merely because
they appear in prediction provenance. Evaluation policy may explicitly request
a semantic conversion such as planar-to-radial depth, with its required side
inputs. An opaque value-only step may be crossed for alignment only if a
validated descriptor guarantees it preserves the plane. An unknown spatial
effect or an unknown effect classification is a hard alignment error.

Use recorded alignment whenever a derivation is declared. Missing references,
unsupported operations, or conflicting metadata must not fall back to
`classify_spatial_alignment`. For legacy heads without lineage, preserve a
clearly identified compatibility path during migration; allow an explicit
alignment override or strict refusal, and record any heuristic policy in
results. Do not manufacture historical provenance from final dimensions. Old
readers can load materialized bytes but are not certified to compare derived
planes; enable producers for evaluation only after capable readers are deployed.

### 7.8 Acceptance criteria

Share JSON descriptors and tiny known-value arrays; contract tests validate
data/schema agreement, loading tests execute operations, crawler tests persist
artifacts, and eval/preprocess tests exercise the cross-package workflow.

| Case | Required result |
|---|---|
| The five-field resize/center-crop example | Export, write, reload, and reconstruct original GT at `320×640`; verify pixel locations, mask semantics, ray policy, and transformed intrinsics/projections. |
| Crop versus resize with identical final sizes | Different plans and sample values; no dimension heuristic can substitute for provenance. |
| Odd source sizes, off-center crop, nonuniform resize, nonzero skew | Exact crop bounds and expected projection coordinates; invalid bounds fail. |
| Materialized reload, repeated access, chained derivation, GT already transformed | No duplicate execution or repeated history; only the verified missing suffix runs. |
| Hierarchical calibration, two cameras, per-frame crops | Correct sensor selected; ambiguous `reduce="first"` fails; cached ancestor calibration stays unchanged; derived calibration has the correct cardinality. |
| Invalid depth, categorical masks, rays, point maps, sparse clouds | Declared modality-specific policies hold; units and pose do not change accidentally. |
| Directory, ZIP, scoped metadata, split/copy, changed IDs, variants | Heads/receipts round-trip; source mappings and referenced records resolve after relocation; sample counts and missing IDs are reported. |
| Torch/Pillow, CPU/GPU, differing worker counts | The selected execution profile is stable; only tested equality/tolerances are claimed; unresolved random parameters cannot be labeled deterministic. |
| Encoding change, quantization, variable output sizes, interrupted/resumed generation | Output metadata matches decoded bytes; incomplete writes are not published as complete; resumes reject conflicting derivations. |
| Unknown operation/version, opaque spatial step, changed source bytes, missing receipt, cycle | Precise refusal before scoring or publishing a strict derivation. |
| Fog or model outputs with spatially transformed inputs | Align only permitted spatial effects; retain clean GT values and explicit output-plane lineage. |
| Current valid/invalid head fixtures and legacy callable transforms | Existing contract acceptance and explicit legacy behavior remain covered; new addon semantic validation is tested separately from core envelope acceptance. |

## Suggested rollout

This order supersedes delaying geometry until after generic normalization.
Changes can ship separately behind opt-in APIs; enable the generation-to-eval
workflow only when its complete reader/writer combination passes conformance.

### Phase 0 — complete the evidence

- Extend the existing contract head corpus and modality inventory; do not
  recreate them. Mark conditional aliases and record output shapes, dtypes,
  units, backend differences, and current calibration behavior.
- Add the five-field resize/crop example and known-value depth/projection cases
  as shared test data. Pin expected crop pixels and the numeric camera example
  in section 7.5 before changing any implementation.
- Verify current directory/ZIP/scoped writer preservation and eval's heuristic
  behavior so migration changes are visible.

Exit: the interoperability failures have reproducible evidence and existing
1.0 fixtures still agree between runtime validation and JSON Schema.

### Phase 1 — descriptors, bindings, and compatibility

- In `euler-dataset-contract`, publish registry lookups and conditional alias
  diagnostics without rewriting keys. Define the opt-in representation and
  `euler_transforms` schemas, typed source/calibration bindings, operation
  version policy, canonical hash rules, and required-feature rejection rules.
- Supply data-only validators and addon schemas from the same definitions;
  test both explicitly because today's schema builder only checks envelopes.
- In `euler-loading`, define resize/crop export and resolution protocols,
  execution profiles, explicit field policies, and output-profile inference.
  Register validators on worker startup as well as in the parent process.

Exit: descriptors round-trip without NumPy/Torch in the contract package;
old readers preserve new addon envelopes, and capable readers reject unsupported
semantics. The original `modality.key` remains required.

### Phase 2 — loading and materialized output

- In `euler-loading`, capture bound per-sample receipts, implement the proposed
  writer arguments and output metadata propagation, and consolidate geometry
  helpers. Add hierarchy-aware calibration output or the typed calibration
  view required by the first consumer.
- In `ds-crawler`, add public validated head/record finalization support where
  needed; preserve per-file mappings and referenced records through save,
  ZIP/scoped output, copy, and split. Do not inspect operation implementations.
- In `euler-preprocess`, route shared preprocessing and actual producer
  receipts through its source-backed backend, including explicit variant
  mappings and output metadata. Start with deterministic crop/resize exports.

Exit: generation, save, reload, and replay match known pixels and calibration;
partial writes, variable sizes, and source-head immutability are covered. Keep
benchmark use opt-in until Phase 3 establishes a compatible evaluator.

### Phase 3 — verified evaluation

- In `euler-eval`, add metadata preflight and output-to-source pairing before
  building joined samples. Ask loading for a forward-only GT alignment plan.
- Replace dimension guessing on the declared-derivation path, align dependent
  fields and intrinsics together, and record support, plans, and legacy policy
  in results and cache keys.
- Run section 7.8's end-to-end cases across all five packages. Publish tested
  minimum versions and migrate benchmark configs explicitly.

Exit: a derived prediction is evaluated against original GT on the correct
plane with no copied crop config and no repeated preprocessing. Unsupported
or unverifiable lineage fails before scores are emitted.

### Phase 4 — expand profiles and adapters from demonstrated needs

- Generalize runtime loader profiles, third-party executor registration, and
  explicit requested profiles. Introduce a bounded adaptation planner with
  declared lossiness policies; retain legacy callables behind known limits.
- Extend supported geometry, value operations, random/data-dependent receipts,
  and divergent-branch alignment only with conformance examples and explicit
  comparison policies. Virtual datasets are a separate capability.
- Measure record size, sampled validation overhead, worker behavior, and
  cache reuse on real datasets before expanding mandatory metadata.

### Phase 5 — a new core contract only if justified

- Promote proven fields only when addons no longer provide the right boundary.
  New structural keys require a declared format version and reader migration.
- Ship deterministic migrations and alias/conflict reports. Historical
  transformations that were never recorded remain unknown unless supplied
  from an authoritative producer record.
- Keep incompatibility diagnostics specific to fields, operations, sources,
  and image planes.

## Design guardrails

- Do not tie semantic identity to a particular loader module, file extension,
  tensor library, or sample key.
- Do not require fixed spatial sizes for datasets that are naturally variable.
- Do not call raw storage range and decoded value range by the same field name.
- Do not silently transpose, rescale, or invert transforms when the input is
  ambiguous.
- Do not turn every useful annotation into a required core field; modality and
  representation profiles should define the relevant subset.
- Do not place package-owned behavior in the shared core when a versioned addon
  is the appropriate boundary.
- Keep materialized history separate from executable loading instructions.
- Derive persisted history from executed, written outputs; configuration alone
  cannot prove execution or correct field binding.
- Preserve the distinction between spatial alignment and changing GT values.
- Make recipe, source, sample, calibration, and execution identity explicit;
  neither equal shapes nor an identical recipe hash proves correspondence.

## What success looks like

A third-party loader should be able to publish a head and output profile, pass
a conformance check, and then work with `euler-loading` and `euler-eval`
without consumer-specific shape or unit patches. A consumer should be able to
reject an incompatible modality before processing a dataset and explain
exactly which axis, dtype, domain, unit, or frame requirement was not met.

For derived datasets, the same guarantee includes history: a producer uses
`SamplePreprocessor`, writes through the dataset writer, and publishes enough
information for a separate evaluator to reconstruct the correct original-GT
view, with matching intrinsics and reported support. Loading the generated
dataset itself applies none of that history a second time. Missing or
unsupported history yields a precise error, not an invented crop or resize.
