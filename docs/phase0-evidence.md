# Phase 0 evidence

Phase 0 is implemented for the reviewed source checkouts and synthetic corpus.
It adds shared data, numerical reference answers, executable consumer checks,
and repeatable inventory capture. Contract 1.0 parsing, defaults, schemas,
decoders, and transformation behavior are unchanged. Transformation descriptors,
receipts, automatic metadata updates, and GT replay were future work at this
baseline. [Phase 1](phase1.md) now implements opt-in descriptors and resolution;
this document retains the original numerical and compatibility evidence.

## Sources and scope

| Source | Reviewed and tested revision | Evidence |
|---|---|---|
| Operator | Dataset list and subsequent clarification | 14 names; `spectral_map` was never used; `spherical_map` carries homogeneous ray directions. |
| `ds-crawler` | `340c228` | Directory/ZIP writers, metadata scopes, hydration, copy, and split. |
| `euler-loading` | `f3db6ff` | 90 CPU/Torch loader declarations, generated loader catalog, preprocessing, calibration reduction, source-backed writing. |
| `euler-preprocess` | `7d79ec2` | Dataset construction, radial conversion, output metadata overrides, variant IDs/attributes, addon hook. |
| `euler-eval` | `7e445fb` | Alignment decisions, camera scaling, depth unprojection, sparse projection, metadata fallback. |

The [operator inventory](../fixtures/inventory/dataset-modality-types.json)
and [loader snapshot](../fixtures/inventory/loader-observations.json) are separate:
an operator name does not imply a matching loader, and a decorator is a
declaration rather than proof of decoded values. The snapshot captures source
SHA-256 hashes, functions, line numbers, literal metadata, shapes, dtypes,
formats, stated units, and both backend declarations. Imported literal constants
are read with AST inspection; no loader source is executed during capture.

Actual dataset bytes and heads were not supplied or scanned. The new heads are
explicitly synthetic metadata examples. They prove acceptance and preservation,
not that every current dataset has the illustrated encoding or units.

## Modality classification

These identities belong to the data-only
[inventory](../euler_dataset_contract/data/modality-inventory-1.0.json).
They do not rewrite `modality.key` or register runtime modalities.

| Operator name | Recorded meaning / proposed identity | Representation evidence and limits |
|---|---|---|
| `rgb` | `appearance.camera.color` | PNG checks decode to float32 in `[0,1]`; CPU HWC, Torch CHW. Other encodings require their own evidence. |
| `spectral_map` | Unused; identity unassigned | No emitted loader type. No spectral semantics invented. |
| `spherical_map` | `geometry.camera.ray_direction`, conditional on `form=ray_map` | Homogeneous directions, with no unit-length promise. Generic decode preserves `(0,0,3)`; resizing as `ray_map` normalizes to `(0,0,1)`. |
| `map_2d` | `signal.grid.scalar` (provisional container identity) | Generic HW float32; no physical unit inferred. |
| `map_3d` | `signal.grid.array` (provisional container identity) | Arbitrary channel count. A five-channel CHW file decodes to HWC on CPU and CHW through Torch. No XYZ assumption. |
| `scattering_coefficient` | `radiometry.scene.scattering_coefficient` | Extinction/scattering coefficient controlling transmission; generic HW float32. The distance unit used in attenuation must be stated separately. |
| `athmospheric_light` | `radiometry.scene.atmospheric_light` | Exact dataset spelling preserved. The emitted loader type is `atmospheric_light`; both spellings have golden heads. Generic float32 HWC/CHW color maps. |
| `sparse_depth` | `geometry.scene.points`, conditional on `form=point_cloud` | Current MUSES/Princeton declarations are clouds with named XYZ and extra columns. MUSES known bytes decode as float64 N×6. A sparse raster elsewhere cannot use this alias without different evidence. |
| `intrinsics` | `geometry.camera.intrinsics` | Generic 3×3 float32; image plane, pixel-center convention, model, and sensor binding remain necessary. |
| `camera_extrinsics` | `geometry.camera.extrinsics` | MUSES declares 4×4 float32, source-sensor to target-sensor. Frame/direction are not inferred from the name; VKITTI's separate `extrinsics` declaration remains N×1 and unresolved. |
| `points_3d` | `geometry.scene.points`, `form=point_map` | Organized dense XYZ derived from a depth image. Generic loaders preserve 3HW on **both** backends, unlike generic `map_3d`. |
| `depth` | `geometry.camera.depth` | Planar/radial and decoded units must be explicit. Checked VKITTI PNG output is HW/1HW float32; head scale is not always honored. |
| `semantic_segmentation` | `semantics.camera.class_labels` | Generic labels are HW uint8, including void 255. VKITTI palette triplets are HWC/CHW int64, not class IDs. |
| `transmission_map` | `radiometry.scene.transmission` | Transmission is distinct from its coefficient. No emitted loader type; axes, value domain, and path definition need dataset evidence. |

This resolves the old spherical-map and sparse-cloud inventory questions for
the reported usage. Container naming, extrinsics interpretation, and migration
policy remain open. No loader alias is added for the misspelled atmospheric
name or for transmission.

## Shared cases

The [manifest](../fixtures/index.json) now enumerates 19 valid/canonical heads,
19 rejection cases, three inventory records, and ten evidence cases. Payloads
label independent reference answers separately from observed legacy behavior.

| Case | What is pinned |
|---|---|
| `tiny-five-field` | Exact RGB/depth/mask pixels and transformed K for 4×8 → 2×4 → 2×2; ray normalization. |
| `documented-five-field` | RGB, depth, mask, intrinsics, and rays for 480×960 → 384×768 → center crop 320×640, with analytic pixel probes. |
| `backend-resize` | Different bilinear filters and nearest-neighbor choices in Torch and Pillow, even for NumPy input. |
| `invalid-depth` | Bilinear resize blends an invalid zero with three valid depth values: observed 3, valid-only reference 4. |
| `pinhole-projections` | Half-pixel camera scaling, odd center crops, nonuniform scaling, explicit offsets, skew, and invalid crop bounds. |
| `depth-projection` | Known planar meters → organized XYZ → projected radial depth; shared with the actual radial producer. |
| `hierarchy-selection` | Lexical `reduce="first"`, wrong-camera ambiguity, source immutability, and preprocess's literal `intrinsics` file-ID convention. |
| `legacy-spatial-alignment` | Equal shapes, multiple-of-eight top-left crop heuristic, resize sampling, crop-origin ambiguity, and legacy depth fallback. |
| `known-values` | Raw uint16 PNG depth, normalized RGB, palette/class-ID distinctions, scalar maps, arbitrary channels, intrinsics, point maps, and cloud values. |
| `source-backed` | Opaque addons, source/variant IDs and attributes, relocated storage, scoped metadata, and stale output dimensions. |

For the documented example, height precedes width throughout. Resize scales
both axes by 0.8; the resolved crop is `[top=32, left=64, height=320, width=640]`:

```text
K_in  = [[800, 0, 479.5], [0, 800, 239.5], [0, 0, 1]]
K_out = [[640, 0, 319.5], [0, 640, 159.5], [0, 0, 1]]
K_out = A_crop @ A_resize @ K_in
x_resize = (x_source + 0.5) * scale_x - 0.5
```

The output depth at `(row=100, col=200)` is `2.981375`, derived independently
from source position `(x=330.125, y=165.125)`. The camera-frame point `(0,0,2)`
projects to `(319.5,159.5)`. The fixture declares its interpolation profile and
numeric tolerances; it does not claim byte equality across arbitrary backends.

## Reproduced interoperability gaps

| Gap | Reproduction and consequence |
|---|---|
| `loading-resize-skew` | Nonuniform resize leaves `K[0,1]=2` instead of 4. Evaluator camera resizing scales this entry, so the helpers disagree. |
| `loader-ignores-head-scale` | VKITTI divides depth PNG values by 100 regardless of head scale; generic dense depth preserves raw values. A millimeter head therefore does not guarantee meter output. The generic per-file scale override does work. |
| `eval-crop-origin` | A centered 10×10 → 8×8 crop needs principal point 3.5; the shape heuristic leaves 4.5. The documented resize-then-crop sequence also differs numerically from resizing directly to the final shape. |
| `writer-copies-source-dimensions` | Loading writes and reloads actual 2×4 RGB bytes while preserving source 4×8 dimensions. The opaque annotation survives, but no transformation history is captured. |
| Backend and validity policies | Torch/Pillow filtering and nearest neighbors differ; depth interpolation blends invalid values. Homogeneous ray magnitude changes when resized as `ray_map`. |
| Calibration selection | Stable lexical reduction can select the wrong camera. The producer's named-file lookup differs from loading's reduction. Cached source matrices remain unchanged in the checked paths. |
| Producer wiring | A `preprocessing` config is currently ignored by the dataset builder. Adding `preprocessors` to the existing loading addon is rejected. Radial conversion does correctly write its `radial_depth=True` override. |
| Legacy depth default | Core metadata construction defaults to planar; evaluator fallback defaults to radial. This fallback test uses an unchecked metadata provider: valid canonical depth heads already require the field. |

Four assertions for the first three gaps use `xfail(strict=True,
raises=AssertionError)`. They must be reviewed when a consumer fix makes them
pass; unrelated exceptions remain failures. Positive baseline assertions also
pin the observed writer, calibration, backend, and producer behavior. These are
an evidence baseline, not acceptance of those behaviors for the future replay
contract. Projection checks currently use zero-skew pinhole unprojection;
general camera-model support is not established by them.

Two pre-existing runtime/schema differences are now explicit. Runtime rejects
reversed RGB ranges, and simultaneous `fileTypes`/`file_types`; the current
JSON Schema accepts those inputs. Their existing invalid fixtures carry
`schema_valid: true` and an explanation. Every canonical golden head satisfies
the generated schema. Resolving these differences is separate from freezing
the Phase 0 baseline; no core schema was silently changed to claim agreement.

## Run and maintain the checks

The normal contract suite uses only the development extra. Consumer checks
ship in `euler_dataset_contract.testing.checks` and run **only when explicitly
selected**. Importing the corpus or pytest plugin does not import NumPy, Torch,
Pillow, OpenCV, or consumer packages.

```bash
uv sync --extra dev --locked
uv run pytest
uv run python scripts/refresh_loader_observations.py /path/to/euler-loading --check

# Use a Python environment with the consumer packages' dependencies and pytest.
# Source checkouts default to sibling repository names; use repeatable
# --repository NAME=PATH overrides for isolated worktrees.
uv run python scripts/check_ecosystem.py \
  --repositories /path/to/checkouts \
  --python /path/to/consumer-venv/bin/python \
  --report /tmp/phase0-results.json
```

Repeat `--target crawler`, `--target loading`, `--target preprocess`, or
`--target eval` to select boundaries. The driver checks import origins, records
source commits/dirty state and dependency versions, verifies the loader snapshot,
and runs each consumer separately. Missing dependencies fail collection;
unexpected skips fail the matrix. It installs nothing and changes no consumer
checkout. Individual environments can also run:

```bash
python -m pytest --pyargs euler_dataset_contract.testing.checks.test_loading -q -rx
```

To refresh declarations, omit `--check`, inspect the snapshot diff, update
affected observations/reference cases deliberately, and rerun the matrix.
The generator also refreshes the existing emitted-vocabulary fixture. Source
hash drift includes helper changes; do not treat a changed decorator as proof
that bytes now conform.

The recorded run used Linux, Python 3.11.2, pytest 9.1.1, NumPy 2.4.6,
Torch 2.12.1, Pillow 12.2.0, and OpenCV headless 5.0.0.93:

| Suite | Passed | Strict expected failures |
|---|---:|---:|
| Contract/data/plugin/distribution checks | 202 | 0 |
| ds-crawler consumer checks | 84 | 0 |
| euler-loading consumer checks | 21 | 3 |
| euler-preprocess consumer checks | 6 | 0 |
| euler-eval consumer checks | 13 | 1 |

These are the shared Phase 0 suites, not the complete upstream test suites.
Torch tensors and the GPU-named decoder modules run on CPU; CUDA execution,
worker-count determinism, real dataset audits, and future receipt replay are
outside this run. Distribution verification follows every manifest reference
in both archives, so packaging cannot silently drop a new evidence case.
