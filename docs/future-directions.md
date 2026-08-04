# Future contract directions

This is a design lookout, not a promise that the next release will implement
every item. It records gaps observed across `euler-dataset-contract`,
`ds-crawler`, `euler-loading`, and `euler-eval`, then proposes an order that can
improve interoperability without invalidating existing dataset heads.

## Where the boundary sits today

The current division of responsibility is useful and should remain:

- `ds-crawler` creates, validates, stores, and hydrates dataset heads alongside
  indexes;
- `euler-dataset-contract` owns the common head model, core metadata fields,
  addon registry, and JSON Schema generation;
- `euler-loading` resolves an `euler_loading` addon, decodes files, matches
  modalities by ID, and applies spatial preprocessing;
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

A hierarchical vocabulary could make relationships obvious, for example
`camera.intrinsics`, `camera.extrinsics`, `geometry.depth`,
`geometry.point_map`, and `labels.semantic`. Dots are not allowed by the 1.0
token grammar, so adopting this directly requires a new contract version or a
separate structured identity such as:

```json
{
  "modality": {
    "key": "intrinsics",
    "identity": {
      "namespace": "camera",
      "name": "intrinsics",
      "version": "1.0"
    }
  }
}
```

Before choosing syntax, inventory all emitted modality names and decide which
are canonical, aliases, or representations. Publish alias resolution as data,
not scattered string heuristics. Keep existing `modality.key` values readable
during a deprecation window and never infer a semantic change solely from a
path or sample key.

## 2. Separate storage, decoded output, and consumer requirements

The 1.0 `meta.dimensions`, `range`, and `scale_to_meters` fields mix concerns.
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
    "representation": "dense_array",
    "axes": ["channel", "height", "width"],
    "shape": {"channel": 1, "height": "H", "width": "W"},
    "dtype": "float32",
    "value_domain": {"unit": "meter", "min": 0, "max": 80},
    "invalid_values": {"non_finite": false, "sentinel": 0},
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
  declares which profiles it accepts.

The contract should support validation at more than one cost level: metadata
only, one decoded sample, or a full dataset scan. Runtime array validation must
be opt-in because checking every sample can be expensive.

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
`camera.extrinsics` should carry `source_frame`, `target_frame`, matrix layout,
and transform direction. Intrinsics should name their camera model and image
plane. A transform should be composable without relying on dataset-specific
loader documentation.

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
deepest calibration entry without knowing its semantic target.

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
3×W×3 array can look both channel-first and channel-last.

## Suggested rollout

### Phase 0 — inventory and fixtures

- Extract every modality key, loader annotation, output shape, dtype, unit,
  frame, and alias currently used by the ecosystem.
- Add shared golden heads and decoded sample descriptors to cross-repository
  tests.
- Resolve inconsistencies in documentation before designing new syntax.

### Phase 1 — non-breaking registry

- Publish canonical modality entries and aliases alongside contract 1.0.
- Expose lookup and deprecation diagnostics without rewriting persisted heads.
- Replace consumer name heuristics with the registry where possible.

### Phase 2 — opt-in representation addon

- Prototype storage/decoded profiles in a versioned addon.
- Add sampled output validation to `euler-loading`.
- Let `euler-eval` declare accepted profiles and use explicit adapters.
- Measure performance and authoring burden on existing datasets.

### Phase 3 — geometry and hierarchy bindings

- Add coordinate-frame and calibration application fixtures.
- Require direction/frame fields only where the semantic modality needs them.
- Verify preprocessing updates both shapes and calibration contracts.

### Phase 4 — contract 2.0 only if justified

- Move proven fields into the core contract.
- Ship a deterministic 1.0 → 2.0 migration tool and alias report.
- Keep readers capable of explaining incompatibilities field by field.

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

## What success looks like

A third-party loader should be able to publish a head and output profile, pass
a conformance check, and then work with `euler-loading` and `euler-eval`
without consumer-specific shape or unit patches. A consumer should be able to
reject an incompatible modality before processing a dataset and explain
exactly which axis, dtype, domain, unit, or frame requirement was not met.
