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
| `meta` | Required for a modality with registered fields; optional and open for an unregistered modality. |

Registered metadata is extensible: extra keys are preserved. This lets a
producer carry dataset-specific details while the registry enforces the shared
minimum.

### `addons`

`addons` is optional. Each key must be a token and each value must be an object
with a syntactically valid `version`. The core package preserves unknown addon
payload fields. If a validator has been registered for that addon name, it is
run against a deep copy of the payload.

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

`skyclass` is an RGB triplet of integers in `[0, 255]`, defaulting to
`[0, 0, 0]`. Both keys exist for compatibility with data already produced by
the ecosystem.

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
