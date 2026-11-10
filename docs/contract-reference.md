# Dataset-head contract reference

This document describes contract version `1.0`. The Python package version is
independent: package releases may fix validation, schema generation, typing, or
documentation without changing the serialized dataset-head format.

## Canonical structure

```json
{
  "contract": {
    "kind": "dataset_head",
    "version": "1.0"
  },
  "dataset": {
    "id": "demo_rgb",
    "name": "Demo RGB",
    "attributes": {
      "ground_truth": true
    }
  },
  "modality": {
    "key": "rgb",
    "meta": {
      "range": [0, 255],
      "dimensions": {"height": 375, "width": 1242, "channels": 3},
      "file_types": ["jpg", "png"]
    }
  },
  "addons": {
    "euler_loading": {
      "version": "1.0",
      "loader": "vkitti2",
      "function": "rgb"
    }
  }
}
```

The top level and the `contract`, `dataset`, and `modality` sections are
closed: unknown keys are rejected. Put generic dataset annotations under
`dataset.attributes`; put consumer-specific behavior in a versioned `addons`
namespace. Modality metadata is deliberately open to additional fields.

## Core fields

### `contract`

| Field | Rule |
|---|---|
| `kind` | Required; exactly `dataset_head`. |
| `version` | Required; numeric `major.minor` or `major.minor.patch`. The current serialized contract is `1.0`. |

`validate_contract_version()` checks version syntax. Contract compatibility is
currently coordinated by producers and consumers; the 1.0 parser does not yet
perform feature negotiation. See the future-directions document for the
proposed compatibility policy.

### `dataset`

| Field | Rule |
|---|---|
| `id` | Required token matching `[A-Za-z_][A-Za-z0-9_]*`. It is the stable semantic dataset identifier, not a path. |
| `name` | Required non-blank display name. |
| `attributes` | Optional object for dataset-level annotations not interpreted by this package. |

### `modality`

| Field | Rule |
|---|---|
| `key` | Required token matching `[A-Za-z_][A-Za-z0-9_]*`. |
| `meta` | Required for a modality with registered required fields; optional otherwise. Always open: extra keys are kept. |

Registered metadata is extensible: extra keys are preserved. This lets a
producer carry dataset-specific details while the registry enforces the shared
minimum.

### `addons`

`addons` is optional. Each key must be a token and each value must be an object
with a syntactically valid `version`. The core package preserves unknown addon
payload fields. If a validator has been registered for that addon name, it is
run against a deep copy of the payload.

`register_addon_validator` also accepts an optional
`head_validator(head, context)` callback. It runs after parsing and normalization,
only when that addon is present, and receives the containing `DatasetHeadContract`.
This lets an addon check references to core fields without changing the existing
two-argument payload validator. Overwriting a registration replaces both callbacks;
omitting `head_validator` removes any earlier head callback for that registration.
`get_registered_addon_head_validators()` returns the registered head callbacks.

### The `euler_loading` addon

`addons.euler_loading` names the euler-loading decoder of a dataset and,
optionally, the modality's experiment role. Its rules live in this package
(`validate_euler_loading_addon`), so every producer and consumer checks heads
the same way:

| Field | Rule |
|---|---|
| `version` | Required, like every addon version. |
| `loader`, `function` | Tokens, set together: the decoder module and the callable in it. |
| `writer_function` | Optional token naming the writer when the naming conventions do not apply. |
| `used_as` | One of `condition`, `input`, `output`, `target`. |
| `slot` | Dotted slot name, e.g. `dehaze.input.rgb`. |
| `task` | Token. |
| `hierarchy_scope`, `applies_to` | Token, and a list of tokens or `"*"`; only with `used_as: condition`. |

Any other key is rejected. The role fields (`used_as`, `slot`, `task`,
`hierarchy_scope`, `applies_to`) are checked by `validate_addon_roles`, which
other ecosystem addons such as `euler_train` can reuse.

Registration is explicit, like the descriptor validators:
`register_euler_loading_addon_validator()` registers the rules once per
process and returns whether it did. It never replaces a validator already
registered for `euler_loading`, so an euler-loading release that extends its
addon keeps its own rules. ds-crawler and euler-loading call it on import.

## Shared metadata

`dimensions`
: Optional non-empty object from semantic axis names to positive integer sizes.
  It describes a single nominal dataset-wide shape; omit it for variable-sized
  data. Axis names use the same token grammar as IDs.

`file_types`
: Optional non-empty list of unique file extensions. Canonical values are
  lowercase and have no leading dot. The runtime parser accepts mixed case,
  surrounding whitespace, and a leading dot, then sorts and normalizes values.
  The legacy input spelling `fileTypes` is also normalized to `file_types`.

`invalid`
: Optional. How pixels without a valid value are marked in the values the
  loader returns: `{"non_finite": boolean, "sentinel": number | null}`, the
  shape and meaning of a representation profile's `invalid`. `sentinel` is the
  finite value that marks an invalid pixel (`null`: none); `non_finite` says
  whether NaN or infinite values can appear, which then mark invalid pixels
  too. Both keys are required.

  | Data | `invalid` |
  |---|---|
  | lidar depth stored with `0` for "no return" | `{"non_finite": false, "sentinel": 0}` |
  | a prediction with NaN holes | `{"non_finite": true, "sentinel": null}` |
  | dense data with no invalid pixels | `{"non_finite": false, "sentinel": null}` |

  Omitting it declares nothing; consumers then apply their own rule (for
  depth, a non-finite or non-positive value is invalid). euler-loading's
  preprocessor resizes a depth or disparity field with a `sentinel` without
  blending invalid pixels into valid ones.

`sparse`
: Optional boolean, default `false`. `true` declares that the raster holds
  measurements at only some of its pixels, as lidar-derived depth or disparity
  does; the rest are invalid as `invalid` declares (without it, consumers take
  `0` for depth).
  Consumers must not interpolate between samples. euler-loading resizes such a
  map by moving each measurement to its nearest target pixel (the nearer
  surface wins), and euler-eval scores predictions on the measured grid.

  ```json
  "meta": {"radial_depth": false, "scale_to_meters": 0.00390625, "range": [0, 65535],
           "invalid": {"non_finite": false, "sentinel": 0}, "sparse": true}
  ```

  A dense map with holes (sky, missing returns) is not sparse; declaring only
  its `invalid.sentinel` keeps the holes out of interpolation without the
  sample-by-sample resize.

`source_grid`
: Optional. How this dataset's pixel grid derives from the grid of the images
  it was computed from: a model's prediction from its input, or a crop or
  resize of a source dataset. Evaluators use it to compare a prediction with
  ground truth on the source grid without guessing whether it was cropped or
  resized.

  ```json
  "source_grid": {"source": "rgb", "size": [400, 879], "affine": [[1, 0, 0], [0, 1, 0]]}
  ```

  `size` is the source `[height, width]`. `affine` maps a source pixel position
  to this grid, with pixel centres at integer coordinates:
  `x' = sx * x + tx`, `y' = sy * y + ty` for `[[sx, 0, tx], [0, sy, ty]]`. It
  is the pixel-grid transform `T` of `K_out = T @ K_in`, so it moves the
  camera too. Only crops and resizes are expressible (positive scales, zero
  off-diagonal terms):

  | Relation | `affine` |
  |---|---|
  | Same grid, or a top-left crop | `[[1, 0, 0], [0, 1, 0]]` |
  | Crop at `(top, left)` | `[[1, 0, -left], [0, 1, -top]]` |
  | Resize `W x H` to `w x h` | `[[w/W, 0, 0.5*w/W - 0.5], [0, h/H, 0.5*h/H - 0.5]]` |
  | Resize, then crop | the crop's matrix times the resize's |

  `source` optionally names what the grid derives from. When the relation
  varies per sample, write it to each file's `attributes.source_grid` instead;
  a file's value overrides the head's. `source_grid_from_rule(rule,
  source_size, size)` builds the matrix for the rules `identity`, `resize`,
  `crop_top_left` and `crop_center`; `resolve_source_grid(head_meta,
  attributes)` reads a sample's grid with that precedence.

Generated schemas describe the canonical serialized form. Compatibility input
aliases such as `fileTypes` are accepted by the Python parser but are not
included in that form.

## Registered metadata

### `rgb`

`range` is a two-element numeric range with `min <= max`. Its default is
`[0, 255]`.

### `depth`

`radial_depth`
: Boolean. `true` means Euclidean distance from the camera center; `false`
  means planar camera-axis depth.

`scale_to_meters`
: Number. Multiply raw depth values by this factor to obtain meters. The
  default is `1.0`.

`range`
: Two-element numeric range in meters with `min <= max`. The historical
  authoring default is `[0, 65535]`.

### `segmentation` and `semantic_segmentation`

`skyclass` is an RGB triplet of integers in `[0, 255]`, or `null`, and
defaults to `null`. The key is required either way. Both modality keys exist
for compatibility with data already produced by the ecosystem.

`skyclass` names the sky label as it appears in the stored segmentation file
viewed as RGB, i.e. the RGB value of a sky pixel:

| Stored map | `skyclass` | Example |
|---|---|---|
| Colour-coded classes | the sky colour | `[90, 200, 255]` (Virtual KITTI 2) |
| Single-channel class IDs (grey PNG, `.npy` / `.npz` label map) | `[v, v, v]` for sky label `v` | `[23, 23, 23]` (Cityscapes label IDs), `[10, 10, 10]` (Cityscapes train IDs) |
| Class ID in one channel of a colour file | the ID in that channel, the other channels' stored values | `[29, 0, 0]` (Real Drive Sim, ID in the red channel) |

Loaders compare this value with the decoded file, so a triple that matches no
sky pixel, such as a colour for an ID map or `[0, 0, v]` for a grey map, makes
every sky mask empty.

`null` leaves the sky undeclared: a loader then uses its own default for the
dataset, or rejects the head if it has none. It is the default because producer
tooling such as `ds-crawler` merges defaults into every head that does not set
the field, and a triple there would read as a declared sky. `[0, 0, 0]` is
always taken literally, as label 0 or black. Earlier releases defaulted to
`[0, 0, 0]`, so heads written before this change can carry it without anyone
having declared it; replace it with the dataset's sky or `null`.

### Geometry: intrinsics, transforms and points

These fields are **optional**. A head may omit them, or omit `meta` entirely,
but a head that declares one must use the shared vocabulary. Their values
match the `euler_representation` profiles and the phase-0 reference heads.

| Keys | Field | Rule |
|---|---|---|
| `intrinsics` | `camera_model` | `pinhole`, `fisheye` or `other`. `pinhole` is an ideal pinhole without distortion coefficients. |
| | `image_plane` | Token naming the image grid the matrix describes, shared with the image modalities it applies to. |
| `camera_extrinsics`, `extrinsics`, `lidar_to_gnss`, `lidar_pose` | `source_frame`, `target_frame` | Non-empty strings naming the frames, e.g. sensor names. |
| | `direction` | `target_from_source` (the matrix maps points from `source_frame` into `target_frame`) or `source_from_target`. |
| `points_3d`, `point_cloud`, `lidar_point_cloud`, `sparse_depth` | `representation` | `point_cloud` (unordered `(N, C)`) or `point_map` (one point per pixel). |
| | `columns` | Non-empty array of unique column names, coordinates first. |
| | `coordinate_unit`, `frame`, `axes` | Non-empty strings, e.g. `meters`, `LIDAR_TOP`, `x right, y forward, z up`. |

The shared `dimensions` field gives a transform's or a matrix's shape, e.g.
`{"rows": 4, "columns": 4}`.

A lidar-to-camera transform, for example:

```json
"modality": {"key": "camera_extrinsics", "meta": {
  "source_frame": "LIDAR_TOP", "target_frame": "camera_optical",
  "direction": "target_from_source", "dimensions": {"rows": 4, "columns": 4}
}}
```

Optional fields are a `MetaFieldDefinition(..., required=False)`. Required fields
remain the default, and the compatibility mapping `MODALITY_META_SCHEMAS` lists
only required ones.

## Normalization and copying

`parse_dataset_head()` and `DatasetHeadContract.from_mapping()` validate and
deep-copy all user-owned dictionaries. `to_mapping()` and
`to_properties_dict()` return detached copies. The convenience accessors
`attributes`, `meta`, and `get_addon()` expose the model's nested dictionaries;
callers that mutate values should copy them first.

Normalization is intentionally small and explicit:

- `fileTypes` becomes `file_types`;
- file types are stripped, lowercased, de-dotted, sorted, and deduplicated;
- no required modality defaults are inserted during parsing.

## Public API by responsibility

| Responsibility | API |
|---|---|
| Parse/model | `DatasetHeadContract`, `parse_dataset_head`, `validate_dataset_head` |
| Metadata registry | `MetaFieldDefinition`, `register_modality_meta_fields`, `get_modality_meta_fields`, `iter_modality_meta_fields`, `build_default_meta` |
| Addon registry | `register_addon_validator`, `get_registered_addon_validators` and the `namespace` aliases |
| Reusable validation | `validate_contract_version`, `validate_addon_version`, `validate_token`, `validate_slot`, `validate_string_list`, `validate_dimensions_dict`, `normalize_meta_dict` |
| JSON Schema | `build_dataset_head_schema`, `build_meta_schema` |

Registries are process-wide. Registration is expected at application startup,
before parsing contracts concurrently.

## Producer and consumer responsibilities

A producer should:

1. build an explicit versioned head;
2. apply authoring defaults if desired;
3. validate before persisting;
4. serialize `DatasetHeadContract.to_mapping()` rather than the unvalidated
   source mapping.

A consumer should:

1. import/register validators for addons it understands;
2. parse before reading semantic fields;
3. request required addons with `required_addons=(...)` when they are essential;
4. reject or ignore unknown addon namespaces according to its own policy;
5. validate decoded arrays separately—the 1.0 head does not guarantee their
   runtime layout or type.
