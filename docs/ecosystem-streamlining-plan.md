# Ecosystem streamlining plan

This document answers a concrete question: **should modality handling be
streamlined into a new `euler-registry` package, or by extending
`euler-dataset-contract`?** It then specifies the design and a staged rollout.

It expands the registry/profile portion of
[Future contract directions](future-directions.md). That document now includes
a subsequent review and the deterministic-transformation design, including
writer propagation and GT replay. Its compatibility decisions and revised
rollout take precedence over the original phase ordering retained here.
The revised Phase 1 is now implemented; [Phase 1 wire format and APIs](phase1.md)
supersedes the older sketches and phase numbering below. Discovery, generic
adaptation, materialized writing, and GT replay remain proposals.

---

## 1. Recommendation in one page

**Extend `euler-dataset-contract`. Do not create `euler-registry`.**

`euler-dataset-contract` is already the universal root of the ecosystem
dependency graph. Every package reaches it, directly or transitively:

```mermaid
flowchart TD
    C["euler-dataset-contract<br/><i>zero runtime deps</i>"]
    C --> DS["ds-crawler"]
    C --> EL["euler-loading"]
    C --> ET["euler-train"]
    C -.->|"[contract] extra"| MN["euler-metric-naming"]
    DS --> EL
    EL --> EE["euler-eval"]
    EL --> EI["euler-inference"]
    EL --> EP["euler-preprocess"]
    MN --> EE
```

A new registry package would add a second root, an edge to seven repositories,
a synchronized release, and a permanent ambiguity about which package owns
modality identity. Extending the existing root costs **zero new dependency
edges**. The package already has the two extension mechanisms
(`register_modality_meta_fields`, `register_addon_validator`), the
`_dataset_contract.py` per-consumer convention, and no runtime dependencies —
exactly the properties a registry needs. `euler-metric-naming` already treats
it as *the* modality authority.

Three refinements to the brief, argued in full below:

| # | The brief said | This plan proposes | Why |
|---|---|---|---|
| 1 | Key is `<domain>.<subject>.<representation>.<quantity>` | Key is `<domain>.<subject>.<quantity>`; representation is a **separate typed field** | Putting representation in the identity forks identity on every encoding change: a fisheye camera would need a new modality, and `semantic_segmentation` would need one id per encoding. §5 |
| 2 | Output format either via a primitives library or user transforms | Declare decoded profiles; a bounded planner selects registered adapters under an explicit consumer policy, or fails with a precise reason | Profiles make preconditions checkable; preserve existing callable ordering and require lineage for spatial alignment. §7 |
| 3 | Extensions propagate by "defining custom modalities on startup" | Shared definition discovery through installed entry points, an env path, or inline data in a head | Parent-process registration alone does not cover independent CLIs or all worker start methods. §6 |

The single highest-leverage change is small and mostly already written:
`euler-loading` annotates **every** loader function with `@modality_meta(...)`
describing dtype, shape, unit and range. Loading already uses the annotated
modality type in some paths, but the full declaration is not an enforced
runtime profile. Promoting it to a validated, contract-owned object is the
basis for planning normalization with explicit preconditions.

---

## 2. What is actually broken today

Every item below was verified against the working trees, not inferred from
documentation. These are the failures a contract has to make impossible.

### 2.1 The head's metadata is validated but not consumed

The contract requires `scale_to_meters` for `depth`
(`euler_dataset_contract/registry.py:192`). No loader reads it. `vkitti2.depth`
declares `scale_to_meters: 0.01` in its annotation and then hardcodes the
conversion:

```python
# euler-loading/euler_loading/loaders/gpu/vkitti2.py:76,84
meta={"raw_range": [0, 65535], "radial_depth": False, "scale_to_meters": 0.01},
...
arr = np.array(Image.open(path), dtype=np.float32) / 100.0
```

A dataset that stores millimetres and correctly declares
`scale_to_meters: 0.001` is silently decoded as centimetres. The contract
validated the field and the loader ignored it. This is the defining failure:
**metadata that no consumer is obliged to honour is decoration.**

### 2.2 The same quantity has three names, and the validated one is unused

| Name | Where | Read by |
|---|---|---|
| `skyclass` | contract, **required** for `segmentation` (`registry.py:164`) | nothing |
| `meta["sky_mask"]` | `generic_dense_depth.sky_mask` (`:156`) | that loader |
| `meta["sky_color"]` | `vkitti2.write_sky_mask` (`:245`) | that writer only — the *reader* hardcodes `(90, 200, 255)` (`vkitti2.py:114`) |

Authoring a valid head for a segmentation dataset therefore produces a field
no code path uses, while the field the loader needs is undeclared.

### 2.3 One declared modality type, several incompatible decoded values

From `loaders.json`, `semantic_segmentation` is emitted by four loaders:

| Loader | dtype | cpu | gpu | Actually returns |
|---|---|---|---|---|
| `generic` | uint8 | HW | HW | class ids |
| `muses` | int64 | HW | 1HW | class ids |
| `real_drive_sim` (`class_segmentation`) | int64 | HW | 1HW | class ids |
| `vkitti2` (`class_segmentation`) | int64 | **HWC** | **CHW** | **raw RGB palette triplets** |

`vkitti2.class_segmentation` returns `(3, H, W)` of RGB values, not labels. The
only discriminator is `meta={"encoding": "rgb"}` inside the decorator — which
lives in a build artifact and never reaches a consumer. A consumer that
correctly handles the other three silently misinterprets VKITTI2.

### 2.4 Identity, cardinality and representation are conflated in the type name

- `extrinsics` (vkitti2, shape `Nx1`, raw `np.loadtxt` output) versus
  `camera_extrinsics` (muses / princeton_dense / real_drive_sim, `4x4`). Same
  semantic quantity, different names *and* incompatible shapes.
  `euler-eval`'s `to_numpy_extrinsics` accepts only `(4,4)` or `(3,4)`
  (`data.py:153`), so VKITTI2 extrinsics cannot be evaluated at all.
- `all_intrinsics` is not a modality — it is `intrinsics` with cardinality
  *many*.
- `calibration` is not a modality — it is a bundle.
- `muses.reference_rgb` maps to type `rgb`. "Reference" is a *role*, not an
  identity; roles already belong in the `used_as` addon field.

### 2.5 Consumers guess, because there is nothing to ask

`euler-loading` infers semantics from substrings of the config name and the
filesystem path (`_metadata.py:213`):

```python
if any(token in lowered for token in ("rgb", "image", "img", "color", "colour")):
    return "rgb"
if any(token in lowered for token in ("depth", "disparity")):
    return "depth"
```

`disparity` is not depth. This also directly violates the existing guardrail
"never infer a semantic change solely from a path or sample key".

`euler-eval` guesses layout from shape and raises on the ambiguous case
(`data.py:88`):

```python
elif arr.shape[0] == 3 and arr.shape[-1] == 3:
    raise ValueError(f"Ambiguous RGB layout for shape {arr.shape}. ...")
```

A 3×W×3 image is simply unloadable — not because the information is missing,
but because it is not carried.

### 2.6 Defaults disagree across the boundary

| Field | `euler-dataset-contract` | `euler-eval` |
|---|---|---|
| `radial_depth` | `False` (`registry.py:190`) | `True` (`data.py:1094`) |

Opposite defaults for a geometry-critical flag, on either side of the seam.

### 2.7 Consumers have invented private, unvalidated meta vocabularies

`euler-eval` reads `representation`, `coordinate_unit` and `columns` from
`modality.meta` (`data.py:1105`). None exist in the registry. They are legal
only because `meta` is open. This is the contract being extended *by
convention*, in exactly the place the plan should formalize.

### 2.8 Automatic third-party loader discovery is missing

`euler-loading` resolves loaders from a hardcoded dict of seven entries
(`_resolution.py:21`). There is no registration path for head-driven discovery.
An explicit `Modality(loader=callable)` already works, but distributing a head
that resolves a new loader automatically requires a registry integration.

### 2.9 The generated schema is vendored and already stale

`euler-view/src/lib/const/ds-crawler.meta.json` is a checked-in copy of
`build_meta_schema()` output. It is missing the `segmentation` modality. Any
consumer outside Python has no live way to obtain the registry.

---

## 3. The model: three contracts, not two

The brief frames this as input versus output. There are three, and the middle
one — the only one that can be checked against reality — is the one that does
not exist today.

```text
stored bytes ──decode──▶ decoded value ──adapt──▶ requested value
     │                        │                        │
 storage profile        decoded profile         requested profile
 (head.modality.meta)   (loader declares)       (consumer declares)
   partly exists      exists only as docs         does not exist
```

| Contract | Owner | Answers | Today |
|---|---|---|---|
| **Storage** | dataset author, in the head | How are the bytes encoded? | `modality.meta`, partial and partly unread (§2.1) |
| **Decoded** | loader author, beside the function | What exactly does this callable return? | `@modality_meta` → build-time JSON only |
| **Requested** | consumer, at call time | What do I need? | nothing; heuristics (§2.5) |

Two consequences follow directly, and they shape the whole plan:

1. **Normalization is a function of decoded → requested.** It cannot be
   implemented generically until *decoded* is machine-readable at runtime. This
   is why promoting `@modality_meta` is the first real step and not a
   nice-to-have.
2. **The decoded profile is partly testable from samples.** Decode a sample to
   check shape, dtype, and observable constraints. Establish units, label
   meaning, and frames with known-value decoder/projection fixtures as well;
   metadata and plausible numeric ranges alone cannot prove those semantics.

---

## 4. Where each piece lives

### 4.1 Repository map

Most phases touch several packages. All repositories are siblings under
`/srv/ao/workspaces/admin/`, each on `main`, each with a
`<repo>-worktrees/` directory alongside it for agent worktrees.

| Repository path | Import package | Distribution | Version | Role in this plan |
|---|---|---|---|---|
| `euler-dataset-contract` | `euler_dataset_contract` | `euler-dataset-contract` | 0.3.0 | **Root.** Registry, identity, profiles, fixtures, CLI |
| `ds-crawler` | `ds_crawler` | `ds-crawler` | 2.10.0 | Producer: authors and persists heads |
| `euler-loading` | `euler_loading` | `euler-loading` | 2.22.0 | Decoder: loader registry, profiles, adapter planner |
| `euler-eval` | `euler_eval` | `euler-eval` | 2.25.0 | Consumer: declares accepted profiles |
| `euler-inference` | `euler_inference` | `euler-inference` | 2.7.0 | Consumer: requests profiles |
| `euler-preprocess` | `euler_preprocess` | `euler-preprocess` | 3.13.0 | Consumer: requests profiles |
| `euler-train` | `euler_train` | `euler-train` | 2.11.0 | Addon owner: shared role vocabulary |
| `euler-metric-naming` | `euler_metric_naming` | `euler-metric-naming` | dynamic | Validates modalities against the registry |
| `euler-view` | `src/` (TypeScript) | — | — | Non-Python schema consumer; stop vendoring (§2.9) |

Paths are relative to `/srv/ao/workspaces/admin/`. A worktree for repo `X`
lives at `X-worktrees/<branch-name>/`.

### 4.2 Ownership

Keep the boundary the ecosystem already has. Add to the root; do not move
behaviour into it.

| Package | Gains | Explicitly does **not** gain |
|---|---|---|
| `euler-dataset-contract` | modality registry, identity grammar, alias map, representation vocabulary, profile model, conformance fixtures, `euler-contract` CLI | NumPy, torch, file I/O, array conversion |
| `euler-loading` | loader **registration**, runtime profile exposure, the adapter planner and its ops, `want=` on `Modality` | modality identity or vocabulary ownership |
| `ds-crawler` | authoring against the registry; explicit alias migration; preservation of derivation heads and referenced records | decoded-side execution |
| `euler-eval` | declares accepted profiles; deletes `to_numpy_*` heuristics | its own meta vocabulary (§2.7 migrates in) |
| `euler-inference`, `euler-preprocess` | request profiles instead of assuming layouts | — |
| `euler-metric-naming` | modality validation against real ids | — |

The contract package stays dependency-free and array-free. It describes and
validates; `euler-loading` executes. This is the existing boundary, and it is
the right one.

---

## 5. Modality identity

### 5.1 Grammar

```text
<domain>.<subject>.<quantity>
```

Three segments, lowercase `[a-z][a-z0-9_]*`, dot-separated. Examples:

```text
geometry.camera.intrinsics
geometry.camera.depth
geometry.scene.points
appearance.camera.color
semantics.camera.class_labels
radiometry.scene.scattering_coefficient
```

- **domain** — the field of meaning: `geometry`, `appearance`, `semantics`,
  `radiometry`, `signal`.
- **subject** — what the quantity is attached to: `camera`, `scene`, or for the
  `signal` domain the index space (`grid`, `sphere`, `set`).
- **quantity** — the measured thing.

### 5.2 Why three segments and not the proposed four

The brief proposed `<domain>.<subject>.<representation>.<quantity>`, e.g.
`geometry.camera.pinhole.intrinsics`. Recommend against, for three reasons:

1. **It forks identity on encoding changes.** A fisheye camera would become
   `geometry.camera.fisheye.intrinsics` — a *different modality*. A consumer
   that wants "the intrinsics" would have to enumerate every camera model that
   exists or will exist. The same failure recurs for
   `semantic_segmentation` (class-id vs RGB palette, §2.3), for depth (planar
   vs radial), and for points (map vs cloud).
2. **It re-creates the exact confusion `future-directions.md` §1 identifies** —
   that the current names mix "true semantic differences, storage/encoding
   differences, and aliases". Encoding in the key is that mixture, promoted to
   syntax.
3. **The registry can no longer answer the useful question.** "Do these two
   datasets hold the same quantity?" becomes a prefix-match with an open tail,
   rather than an equality test.

Representation is typed, queryable, and free to vary without touching identity.
This conceptual core-shape sketch would need a new format version; §5.4
describes the addon route compatible with unchanged 1.0 readers:

```json
{
  "modality": {
    "id": "geometry.camera.intrinsics",
    "representation": {"model": "pinhole", "layout": "matrix_3x3"}
  }
}
```

This satisfies "simple without infringing on exactness" better than the
four-segment form: the id stays short and stable, and exactness moves to a
place where it can carry constraints (`fx > 0`, `image_plane`, units) that a
name segment never could.

### 5.3 Starter registry

The full mapping of everything the ecosystem emits today. `alias` entries stay
readable and resolvable through a deprecation window; they are never silently
rewritten.

| Legacy name(s) | Modality id | Representation carries |
|---|---|---|
| `rgb` | `appearance.camera.color` | `layout`, `value_domain`, `color_space` |
| `rccb` | `appearance.camera.color` | `filter_array: rccb`, `channels` |
| `depth` | `geometry.camera.depth` | `depth_kind: planar_z\|radial`, `unit`, `invalid` |
| `intrinsics` | `geometry.camera.intrinsics` | `model`, `layout`, `image_plane` |
| `all_intrinsics` | `geometry.camera.intrinsics` | *(cardinality `per_sensor`, §8)* |
| `extrinsics`, `camera_extrinsics` | `geometry.camera.extrinsics` | `layout`, `direction`, `source_frame`, `target_frame` |
| `calibration` | *(composite — a binding, not a modality)* | — |
| `points_3d` | `geometry.scene.points` | `form: point_map`, `axes` |
| `point_cloud`, `lidar_point_cloud` | `geometry.scene.points` | `form: point_cloud`, `columns` |
| `sparse_depth` | `geometry.scene.points` **when the declared value is a cloud**; `geometry.camera.depth` for a sparse depth raster | explicit `form`, `columns` or raster validity/units; ambiguous uses remain unresolved |
| `scene_flow` | `geometry.scene.flow` | `axes`, `unit` |
| `segmentation`, `semantic_segmentation`, `class_segmentation`, `semantic_segmentation_color` | `semantics.camera.class_labels` | `encoding: class_id\|rgb_palette`, `palette`, `label_space` |
| `instance_segmentation` | `semantics.camera.instance_labels` | `encoding` |
| `panoptic_segmentation` | `semantics.camera.panoptic_labels` | `encoding` |
| `sky_mask` | `semantics.camera.mask` | `class: sky` |
| `atmospheric_light`, `athmospheric_light` | `radiometry.scene.atmospheric_light` | `axes`, `value_domain`; preserve the literal dataset spelling |
| `scattering_coefficient` | `radiometry.scene.scattering_coefficient` | `axes`, `unit`, `distance_unit` |
| `transmission_map` | `radiometry.scene.transmission` | `axes`, `value_domain`, `path_definition` |
| `sh_coeffs` | `radiometry.scene.sh_coefficients` | `order`, `basis` |
| `map_2d` | `signal.grid.scalar` | `axes`, `unit` |
| `map_3d` | `signal.grid.array` | arbitrary channels/axes; no fixed XYZ count |
| `spherical_map` | `geometry.camera.ray_direction` when `form=ray_map` | `axes`, `normalization`, `frame`, `image_plane`, `projection` |
| `spectral_map` | *(unused; no identity assigned)* | operator confirmed it was never used |

Three things this table settles that the current names cannot:

- The reviewed `euler-eval` sparse-depth path projects a point cloud into the
  prediction plane. This supports a conditional mapping for that path, not a
  universal alias for every dataset named `sparse_depth`.
- `all_intrinsics` and `calibration` are **not modalities**. They are
  cardinality and bundling, handled by binding (§8).
- `sky_mask` generalizes to `semantics.camera.mask` with a class parameter, so
  a road mask or vehicle mask needs no new modality.

The operator clarified `spherical_map` as homogeneous ray directions, without
a unit-length guarantee, and confirmed sparse 3D depth and organized
`points_3d`. These are recorded in [Phase 0 evidence](phase0-evidence.md).
Whether `signal.*` should use subject-as-index-space remains open (§12).

### 5.4 Introducing identity without changing the 1.0 core shape

Contract 1.0's `modality.key` is a token; dots are rejected by `_TOKEN_PATTERN`
and a test asserts it (`tests/test_registry.py:35`). The `modality` object is
also closed and `key` is required. Adding `modality.id`, even alongside `key`,
breaks unchanged readers and the published 1.0 schema.

- Keep `modality.key` and introduce richer identity in a versioned
  `addons.euler_representation` payload, as sketched in
  [Future contract directions](future-directions.md#1-establish-a-canonical-modality-vocabulary).
- Resolve only unambiguous aliases, and report conflicts between the legacy
  key, identity, and representation. Never invent a reverse alias for a new id.
- Offer canonical identity through a lookup/accessor without silently rewriting
  persisted heads. New readers can continue accepting old heads.
- Direct structural fields such as the §5.2 sketch require an explicitly
  versioned core format and reader migration if eventually adopted.

---

## 6. Extensibility without plumbing

The brief's open question — "I am not sure how to propagate this definition
through the packages" — is the crux. In-memory registration in the parent is
insufficient across all worker start methods and independent CLI processes.
An application can register definitions in each process; a shared discovery
protocol makes that initialization repeatable across consumers.

Use **definitions as data**, discovered by the contract package. Each process
loads the same installed or configured definitions at registry initialization;
workers must also register the addon validators they need. Installed entry
points can import trusted package code; inline head definitions cannot.

Four sources, in precedence order (later wins, conflicts are an error unless
explicitly overriding):

**1. Built-in** — the starter registry of §5.3, shipped in the package.

**2. Packaging entry points** — the primary extension path.

```toml
# a researcher's own pyproject.toml — the entire integration
[project.entry-points."euler_dataset_contract.modalities"]
my_lab = "my_lab.modalities:MODALITIES"
```

`pip install my-lab-modalities` is the whole install step. No euler package
changes. Works in subprocesses and worker processes because it is resolved from
the environment, not from process state.

**3. `EULER_MODALITY_PATH`** — colon-separated JSON/TOML files, for unpackaged
local work and for injecting definitions into a job without editing code.

**4. Inline in the head** — a dataset carries its own definition:

```json
{
  "modality": {"key": "depth_uncertainty", "meta": {"unit": "meter"}},
  "addons": {
    "euler_representation": {
      "version": "1.0",
      "modality_id": "geometry.camera.depth_uncertainty",
      "definition": {
        "version": "1.0",
        "description": "Per-pixel depth standard deviation.",
        "meta_fields": {"unit": {"type": "string", "required": true}},
        "decoded": {"axes": ["height", "width"], "dtype": "float32"}
      }
    }
  }
}
```

An inline definition makes a novel modality describable and checkable by a
reader supporting that schema. Loading and normalization still require
compatible installed decoders and adapters; data alone supplies no executable
implementation. Definitions are scoped to that head, may not override a
registered id, and are reported as unregistered by tooling that cares.

Python `register_modality(...)` remains for genuinely dynamic cases, and the
existing `register_modality_meta_fields` keeps working as a thin shim.

---

## 7. Normalization: declare profiles, plan the adapters

### 7.1 The profile

One shape describes both sides of the seam. Storage uses the `storage` block,
loaders the `decoded` block, consumers a `requested` block with the same
grammar and every field optional (an omitted field means "don't care").

```json
{
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

Named axes make HWC and CHW unambiguous. Symbolic dimensions (`"H"`) allow
variable resolution with cross-field constraints. The dtype vocabulary is small
and library-independent.

### 7.2 The planner, not a converter library

The brief asked whether conversion should be a primitives library in
`euler-loading` or left to user transform functions. Reuse tested primitives
in a bounded planner so consumers can inspect a checked plan instead of
rebuilding common adapter chains. Arbitrary callables still need explicit
descriptors for their effects; they can be tested, but cannot be inferred from
the function's presence in a transform list.

Instead: given a declared `decoded` profile, a `requested` profile, and the
consumer's permitted effects, `plan_adaptation` returns an ordered list of
registered operations, or raises with the exact field that could not be
satisfied. Spatial crop/resize additionally requires correspondence and
executed lineage; a profile delta cannot establish the correct image plane.
See [the transformation design](future-directions.md#7-persist-deterministic-transformations-from-generation-to-evaluation).

```python
plan_adaptation(vkitti2_depth_profile, {"axes": ["height", "width"],
                                        "value_domain": {"unit": "meter"}})
# [SqueezeAxis("channel")]

plan_adaptation(vkitti2_semseg_profile, {"semantics": {"encoding": "class_id"}})
# UnsatisfiableProfile: semantics.encoding: have 'rgb_palette', want 'class_id';
#   adapter 'palette_to_class_id' requires representation.palette, which the
#   dataset head does not declare.
```

The op set is small and closed, each op declaring preconditions, output profile
delta, lossiness and required side inputs: `TransposeAxes`, `SqueezeAxis`,
`ExpandAxis`, `CastDtype`, `ScaleUnit`, `NormalizeDomain`,
`PaletteToClassId`, `PlanarToRadial` (needs intrinsics), `DepthToPointMap`
(needs intrinsics), `Affine3x4To4x4`, `PointMapToCloud`.

Properties that matter:

- **Refusal beats guessing.** The 3×W×3 case (§2.5) is resolved by declaration;
  where it genuinely is not, the error names the missing field instead of
  guessing. This directly implements the guardrail "do not silently transpose,
  rescale, or invert transforms when the input is ambiguous".
- **The plan is inspectable before any array is touched** — printable, and
  assertable in tests.
- **Ops and compositions are testable.** Verify individual pre/postconditions
  and representative chains, including order-dependent and lossy behavior.
- **User transforms stay.** Preserve the ordering of existing callable paths.
  New normalization stages are explicit; an opaque callable cannot promise a
  post-transform profile or replayable history without a checked descriptor.

### 7.3 The call site

```python
Modality("/data/vkitti2/depth", want="geometry.camera.depth@planar_meters_hw")
```

`want=` accepts a named preset (registry-owned, versioned) or an inline
profile dict. Presets exist so the common case is one short string, and so a
lab can name its house convention once.

---

## 8. Binding: which value applies to what

Beyond identity, the unresolved cases are §2.4's `all_intrinsics` and
`calibration`, plus hierarchical calibration inheritance. These are **binding**
concerns. Shared geometric meaning belongs in typed representation/derivation
descriptors; loading-specific resolution remains in its versioned addon. The
current `euler_loading` validator rejects new keys, so these are proposed
concepts rather than fields that can be inserted into its 1.0 payload:

| Field | Meaning |
|---|---|
| `cardinality` | `one`, `per_sensor`, `many` — replaces `all_intrinsics` |
| `applies_to` | target modality ids or sensor frames — already exists, now typed against the registry instead of free strings |
| `hierarchy_scope` | levels at which the value may be defined — already exists |
| `frame` | `source_frame` / `target_frame` identifiers for transforms |
| `direction` | `target_from_source` or `source_from_target` |

This removes the name-based assumption of "first or deepest calibration entry"
and makes `euler-eval`'s extrinsics handling checkable. A `calibration` bundle
becomes several bound values, each with its own identity, rather than an opaque
dict.

Note that `euler_loading` and `euler_train`'s addon validators are already
near-duplicates (`used_as`, `slot`, `hierarchy_scope`, `applies_to`, `task`).
Factor the shared role vocabulary into the contract package and have both
addons compose it, rather than adding a third copy.

---

## 9. Verification

"Robust and verifiable" needs a mechanism, not a convention.

**9.1 Shared fixture corpus.** Golden heads and decoded-sample descriptors ship
inside `euler-dataset-contract` and are exported as a pytest plugin
(`euler_dataset_contract.testing`). Every repo's CI runs the same fixtures, so a
contract change cannot pass in one repo while breaking loading or evaluation.
This closes the gap `future-directions.md` §5 identified but did not staff.

The head corpus, the plugin, and the rule that a contract change is proven
against them in every repo before it ships exist as of Phase 0 and are
documented in [Conformance fixtures](conformance-fixtures.md). Decoded profiles and descriptor fixtures now ship in the revised Phase 1;
automatic loader profile publication and materialized writing remain later work.

**9.2 Runtime conformance, opt-in and tiered.** Checking every sample is
expensive, so cost is explicit:

| Level | Cost | Checks |
|---|---|---|
| `metadata` (default) | bounded parsing, no array decode | head parses; declared profiles are coherent |
| `sample` | one decode | the decoded value matches the loader's declared profile |
| `scan` | full pass | invariants hold across the dataset |

**9.3 The CLI.** A proposed `euler-contract check <dataset> --level metadata`
validates descriptors without array dependencies. Sample/scan checks require
an explicitly installed loading integration, or a loading-owned command.
Decoded checks can detect shape/dtype and observable profile violations;
known-value depth, palette, and projection fixtures are required to establish
correct scaling and geometry. A plausible range alone cannot detect §2.1.

**9.4 Publish the schema.** Generated JSON Schema is published as a release
artifact rather than vendored, so `euler-view` and other non-Python consumers
stop drifting (§2.9).

---

## 10. Rollout

The original registry work breakdown follows. The revised delivery order is
in [Future contract directions](future-directions.md#suggested-rollout): geometry,
bindings, and deterministic writer/evaluator integration precede general
spatial normalization. Packages may ship opt-in support independently, but
producers must not enable a workflow until the required readers pass shared
conformance with them.

### Phase 0 — Inventory and fixtures *(no behaviour change)*

*Touches:* `euler-dataset-contract` (all code); CI config only in `ds-crawler`,
`euler-loading`, `euler-eval`, `euler-inference`, `euler-preprocess`,
`euler-train`, `euler-metric-naming`.

- Land §5.3's table as data, with the evidence in §2 as regression fixtures.
- Add the shared fixture corpus and the pytest plugin.
- Wire the fixtures into all seven Python repos' CI.

Ships: nothing user-visible. Buys: a safety net for everything after.

### Original Phase 1 — Registry and identity *(superseded)*

The implemented Phase 1 spans contract and loading, including profiles,
bindings, canonical hashes, and resize/crop resolution. See [its finalized
scope](phase1.md). The following original outline is retained as planning
history; its discovery and CLI items are not claims of implementation.

*Touches:* `euler-dataset-contract` only.

- Modality registry: id grammar, alias map, `register_modality`, lookup and
  deprecation diagnostics.
- Discovery: entry points, `EULER_MODALITY_PATH`, inline definitions.
- Canonical identity lookup and an opt-in representation addon, retaining the
  required `modality.key`; no new structural fields under contract 1.0.
- `euler-contract` CLI at `--level metadata`.
- Fix §2.6: reconcile the `radial_depth` default and pin it in a fixture.

Ships: heads may carry canonical ids in the addon; existing keys stay readable.

### Phase 2 — Decoded profiles become real *(the load-bearing phase)*

*Touches:* `euler-dataset-contract` (profile model), `euler-loading` (annotations,
loader registry, profile exposure).

- Move the profile model into the contract package.
- `@modality_meta` gains profile fields and is **validated at import**, not at
  generate time. `loaders.json` becomes a generated view of a runtime registry
  rather than the only copy.
- `euler-loading` exposes `Modality.decoded_profile` and
  `MultiModalDataset.profiles()`.
- Loader registration: entry-point group `euler_loading.loaders`, replacing the
  hardcoded dict (§2.8). Third-party loaders become possible here.
- `euler-contract check --level sample`. Fix the defects it reports —
  §2.1, §2.3 and §2.4 are expected to fail on first run, which is the point.

Ships: every built-in loader truthfully declares what it returns, checkably.

### Phase 3 — Normalization

*Touches:* `euler-loading` (planner, ops, `want=`), `euler-eval`,
`euler-inference`, `euler-preprocess`.

- Adapter ops and `plan_adaptation` in `euler-loading`.
- `want=` on `Modality`; named profile presets in the registry.
- `euler-eval` declares accepted profiles and deletes `to_numpy_*` heuristics
  (§2.5), migrating its private meta vocabulary (§2.7) into declared
  representation fields.
- `euler-inference` and `euler-preprocess` request profiles instead of assuming
  layouts.

Ships: "give me this format" works, and refuses precisely when it cannot.

### Phase 4 — Geometry, binding, and governance

*Touches:* `euler-dataset-contract` (typed fields, role vocabulary),
`euler-loading` and `euler-train` (addon validators compose it),
`euler-preprocess` (calibration-aware preprocessing), `euler-view` (published
schema instead of vendored).

- `frame`, `direction`, camera model and image plane as typed fields.
- Binding model (§8); shared role vocabulary factored out of the two duplicated
  addon validators.
- Verify preprocessing updates shapes *and* calibration together.
- Version negotiation policy: minor-version tolerance, capability advertisement,
  alias deprecation windows.

### Phase 5 — Contract 2.0, only if justified

*Touches:* all repositories in §4.1.

- Promote proven fields to core; deterministic 1.0 → 2.0 migration with an
  alias report; readers that explain incompatibilities field by field.

---

## 11. Guardrails

Inherited from `future-directions.md` and still binding:

- Semantic identity is never tied to a loader module, file extension, tensor
  library, or sample dict key.
- No fixed spatial sizes for naturally variable datasets.
- Raw storage range and decoded value range never share a field name.
- Never silently transpose, rescale, or invert when the input is ambiguous —
  refuse, and name the missing field.
- Not every useful annotation becomes a required core field.
- Package-owned behaviour stays in a versioned addon.

Added here:

- **The contract package never imports NumPy or torch.** It describes and
  validates; `euler-loading` executes.
- **Declared and actual must be checkable.** A field no consumer is obliged to
  honour, and no check can falsify, does not go in — that is what produced
  §2.1 and §2.2.
- **Extension is data first, code second.** If it needs a Python call at
  startup to work, it will not survive a worker process.
- **Aliases resolve as data, in one place.** Never as scattered string
  heuristics.
- **Additive until proven.** Every phase leaves existing heads valid.

---

## 12. Open questions

These need an owner decision; guessing them into the design would be worse than
leaving them marked.

1. **`signal.*` subject slot.** For `signal.grid.scalar` the subject is an index
   space, not a subject. Accept the mild inconsistency, or introduce a fourth
   domain convention for container-typed signals?
2. **Resolved for reported usage: `spherical_map`.** A homogeneous ray
   direction map; projection and normalization remain representation facts,
   with no unit-vector guarantee inferred from its name.
3. **Resolved conditionally: `sparse_depth`.** Reviewed MUSES/Princeton
   declarations and evaluator projection use point clouds, consistent with the
   operator's sparse 3D depth. Sparse rasters elsewhere still require a distinct
   representation and cannot silently inherit this alias.
4. **`vkitti2.read_extrinsics` shape `Nx1`.** Is this a real dataset format that
   needs a representation, or a latent bug to fix in Phase 2?
5. **Preset naming.** Are profile presets (`@planar_meters_hw`) versioned
   independently of the modality registry?
6. **Deprecation window.** How long do legacy `modality.key` values stay
   readable — one minor, one major, or indefinitely?

---

## 13. What success looks like

Unchanged from `future-directions.md`, now with a mechanism behind it:

> A third-party loader publishes a head and an output profile, passes
> `euler-contract check --level sample`, and then works with `euler-loading`
> and `euler-eval` without consumer-specific shape or unit patches. A consumer
> rejects an incompatible modality before processing and explains exactly which
> axis, dtype, domain, unit, or frame requirement was not met.

Concretely, at the end of Phase 3, all of the following hold and are tested:

- A depth dataset storing millimeters and declaring `scale_to_meters: 0.001`
  decodes to meters correctly, demonstrated by known-value fixtures, or fails
  loudly — §2.1 cannot recur.
- `semantics.camera.class_labels` from VKITTI2 and from MUSES normalize to the
  same requested profile, or refuse with a named missing field — §2.3.
- Adding a modality definition requires an entry point or inline data; novel
  executable behavior additionally requires an installed registered loader or
  adapter, with no edits to built-in dispatch tables — §2.8.
- No consumer infers meaning from a path, a config name, or an array shape —
  §2.5.
