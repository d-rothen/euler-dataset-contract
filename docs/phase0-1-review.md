All five findings have been corrected in the contract and companion loading
worktrees. The changes add focused validation and numerical fixes within the
existing Phase 1 design. Core-only readers and ordinary callable loading retain
their compatibility behavior.

| Finding | Applied correction |
|---|---|
| Wrapped decoder identity | Dataset export verifies the actual function against the supported built-in module, rejecting copied names and decorator metadata. |
| Contradictory head identity | Addon registration has an optional containing-head callback; strict representation readers use the shared alias resolver to check identity and form. |
| Identifier grammar | Runtime and generated schemas require exactly three modality-ID segments and reject trailing characters in IDs/tokens/digests. |
| Pillow boolean threshold | Boolean values are thresholded while interpolation results are still floating point; integer truncation remains unchanged. |
| Integer crop refusal | Precision checks follow resolved operation sizes, allowing exact crops/identity resizes while still refusing int32/int64 interpolation. |

Regression tests reproduced the original failures before the fixes. They also
cover opt-in versus envelope-only parsing, conditional/provisional/custom aliases,
callback replacement, ordinary wrapped-loader execution, integer source
immutability, crop-then-resize ordering, and the existing integer rounding policies.

The original review findings follow. Their code locations refer to the reviewed
snapshot; the validation results at the end describe the amended implementation.

This review covers contract commits `c6c8cd4` and `5f99154`, the streamlining
plan, its revised rollout in `future-directions.md`, and the finalized
`phase1.md` specification. The loading integration was also inspected and
tested in its `streamline-phase-1` worktree. Those loading changes are still
uncommitted on base `f3db6ff`; they are not part of either contract commit or
the loading main branch. The findings below distinguish their locations.

1. **[P1] Verify the actual decoder callable when exporting a dataset plan.**

   Location: companion loading source,
   `euler_loading/transform_descriptors.py`, lines 313–322.

   `_check_dataset_bindings` identifies a loader only by its `__module__` and
   `__qualname__`, then checks the `euler_loading.loaders.` prefix. A normal
   `functools.wraps` decorator preserves both attributes. Consequently, a
   user-supplied decoder with additional effects passes the check as a built-in.

   Reproduction: use the single-RGB dataset/bindings setup from
   `test_dataset_export_includes_entire_chain`, and construct one dataset with
   the built-in loader and another with this loader:

   ```python
   @functools.wraps(generic_dense_depth.rgb)
   def scaled_rgb(*args, **kwargs):
       return generic_dense_depth.rgb(*args, **kwargs) * 2
   ```

   Both `export_transform_plan` calls succeed and return equal descriptors.
   The first output pixel is approximately `[0.05294118, 0.05686275, 0.06078432]`
   for the built-in and `[0.10588235, 0.11372549, 0.12156864]` for the wrapper.
   Shape/dtype validation cannot detect the omitted effect. This breaks the
   explicit promise that dataset export rejects opaque decoder callables and
   includes the complete effective input boundary.

   Compare the callable itself against the supported built-in registration,
   and bind its supported decoder version. Reject unknown wrappers unless their
   effects are explicitly described. Unwrapping a function and treating it as
   the original would still omit those effects. Add a regression using a
   wrapped built-in, not just a lambda with an unrelated name.

2. **[P1] Connect strict representation validation to the containing head.**

   Location: [descriptors.py](../euler_dataset_contract/descriptors.py),
   lines 372–377 and 388–401.

   Registering the new validators checks each addon in isolation. The strict
   head-reading path never compares `modality.key` with the representation
   identity. The independent `resolve_modality` API knows about the conflict,
   but nothing in this path invokes it.

   This reproduces in the contract package alone:

   ```python
   from euler_dataset_contract import parse_dataset_head, register_descriptor_validators
   from euler_dataset_contract.testing import descriptor_fixture, golden_heads

   register_descriptor_validators()
   head = next(case.head for case in golden_heads() if case.name == "rgb-minimal")
   head["addons"] = {
       "euler_representation": descriptor_fixture("five-field")["representation"]
   }
   parsed = parse_dataset_head(head)  # Succeeds: key=rgb, identity=geometry.camera.depth.
   ```

   The addon has a valid depth profile, so its internal identity/kind check
   also passes. Meanwhile, `resolve_modality("rgb",
   declared_id="geometry.camera.depth")` returns `status="conflict"`.
   Capable readers can therefore disagree about the quantity in the same
   supposedly validated head. This is directly contrary to the plan's
   requirement to diagnose conflicts between legacy keys and canonical identity.

   Add a head-aware validation step for readers opting into descriptors. It
   should reject known identity/representation conflicts using the shared
   registry while preserving the existing behavior for readers that have not
   opted in. Standalone addon validation cannot enforce this invariant because
   its callback does not receive the containing head.

3. **[P2] Enforce the agreed identifier grammar in the descriptor definitions.**

   Location:
   [_descriptor_definitions.py](../euler_dataset_contract/_descriptor_definitions.py),
   lines 43–45 and 541–545.

   The new modality-ID pattern uses `{2,}`, allowing four or more segments;
   the plan and existing inventory tests require exactly three. For example,
   `geometry.camera.pinhole.intrinsics` is accepted as a representation ID,
   including with an image profile because it misses the known-intrinsics
   identity check. It also restores precisely the representation-in-identity
   form that section 5.2 rejects.

   There is a second grammar inconsistency at this boundary: `re.search` with
   the trailing `$` permits a final newline. Both `SourceBinding` with
   `dataset_id="rgb\n"` and `RepresentationAddon` with
   `modality_id="geometry.camera.depth\n"` are accepted. The unchanged core's
   `validate_token("rgb\n", ...)` correctly rejects the former; the latter
   also evades the exact known-identity kind constraint. The generated schemas
   share these permissive patterns.

   Use exactly three segments and a true end-of-input constraint consistently
   in runtime and generated schemas. Test externally authored IDs and tokens,
   including trailing newlines, rather than only the shipped inventory.

4. **[P2] Apply the Pillow boolean threshold before casting to boolean.**

   Location: companion loading source,
   `euler_loading/transform_descriptors.py`, lines 546–556.

   The Pillow branch casts every non-floating output to the original dtype
   before the boolean-threshold branch runs. For boolean arrays, that turns
   any nonzero interpolated value into `True`, discarding the value needed to
   honor `mask_threshold`.

   Reproduction: resolve a Pillow recipe for a `generic`, `HW`, boolean 2×2
   field, bilinear resize to 1×1, and `mask_threshold=0.5`. Input
   `[[True, False], [False, False]]` produces `True`. The same Pillow operation
   with a float32 profile produces `0.25`, which should fail the declared
   threshold. Both the descriptor and output validation accept the boolean
   result. This is a threshold-order error within one backend; it does not
   depend on a cross-backend equality claim. Categorical `kind="mask"`
   profiles require nearest sampling, so this affects the other supported
   boolean field profiles that permit bilinear sampling.

   Exclude booleans from the early integer conversion and apply their threshold
   to the floating interpolation result. Preserve the separately declared
   legacy integer-truncation behavior for actual integer arrays.

5. **[P2] Restrict the integer precision refusal to operations that interpolate.**

   Location: companion loading source,
   `euler_loading/transform_descriptors.py`, lines 418–422.

   `_check_support` rejects every int32/int64 profile, including plans that
   contain only a crop. Cropping uses a copied array and a slice; it never
   passes these values through float32. This unnecessarily blocks exact crops
   of class-ID arrays, including the int64 segmentation output recorded in
   the Phase 0 inventory.

   Reproduction: a nearest-policy `mask` profile with dtype `int64`, shape
   `[2, 2]`, and a single crop to `[1, 1]` is accepted by `TransformsAddon`.
   Resolution then raises `this float32 executor does not support int32/int64
   profiles` before it can slice the sample. The documented restriction is
   on passing those types through float32 interpolation.

   Make this check depend on whether the resolved chain performs an actual
   resize. Retain the rejection for the current float32 resize implementation;
   test crop-only and identity-resize cases with integer labels that cannot be
   represented exactly in float32.

Phase 0 is a useful evidence baseline. The numerical reference answers are
separate from observed legacy results, known failures use strict expected
failures, the corpus exercises real consumer code, and the inventory avoids
inventing meanings for conditional or unused names. No new Phase 0 blocking
defect was found in the reviewed changes.

The revised sequencing also makes sense: retaining token-valued 1.0 heads,
using opt-in addons, keeping array execution out of the contract, and separating
planned computation from materialization all preserve useful boundaries.
Receipts, writer metadata propagation, and evaluator replay are clearly deferred
and were not treated as missing Phase 1 implementations. The fixes above should
close the declared Phase 1 guarantees before those later stages build on them.

Two rollout limits remain relevant. Consumer checks are opt-in and are not yet
wired across all consumer CI jobs, as `conformance-fixtures.md` acknowledges.
The successful matrix below is a local run, not evidence of continuous coverage
in all seven Python consumers. Also, reproducing the loading results requires
the companion source changes; checking out the two contract commits alone does
not supply them.

Validation after the amendments on Linux/Python 3.11.2:

| Check | Result |
|---|---|
| Contract test suite | 309 passed |
| Companion loading complete unit suite | 545 passed; 15 real-dataset tests deselected |
| Shared crawler checks | 88 passed |
| Shared loading checks | 21 passed; 3 strict expected failures |
| Shared preprocess checks | 6 passed |
| Shared eval checks | 13 passed; 1 strict expected failure |
| Loader observation snapshot | All 90 declarations current |
| Contract lock, Ruff, generated schemas, generated Phase 1 fixtures | Passed |
| Contract wheel/sdist build, archive verification, Twine | Passed |
| Loading wheel/sdist build and Twine | Passed |
| Installed contract wheel without optional dependencies | Strict head rejection and all 20 golden heads passed |
| Generated modality-ID pattern in JavaScript | Valid ID accepted; extra segments and trailing line breaks rejected |
| Regression coverage for findings 1–5 | Passed; original failures reproduced before fixes |

The four expected failures are the previously documented skew, depth-scale,
and evaluator crop-origin cases. Real datasets, CUDA parity, and the future
materialized workflow were not verified. The pre-existing `package-lock.json`
modification was left untouched. The loading fixes amend its existing
`streamline-phase-1` worktree; its unrelated source changes were preserved.
