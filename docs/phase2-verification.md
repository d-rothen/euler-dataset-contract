# Phase 2 implementation and verification

Verified on Python **3.11.2**, Linux, using CPU execution. These coordinated
package versions are **unreleased**. No release, merge into a main checkout,
benchmark generation, or evaluator integration was performed.

## Source trees

All Phase 2 work is on the `streamline-phase-2` branch in these worktrees:

| Package | Version | Exact worktree | Baseline commit |
|---|---|---|---|
| euler-dataset-contract | 0.5.0 | `/srv/ao/workspaces/admin/euler-dataset-contract-worktrees/streamline-phase-2` | `f37f85d` |
| euler-loading | 2.24.0 | `/srv/ao/workspaces/admin/euler-loading-worktrees/streamline-phase-2` | `f3db6ff` plus reviewed Phase 1 source |
| ds-crawler | 2.11.0 | `/srv/ao/workspaces/admin/ds-crawler-worktrees/streamline-phase-2` | `340c228` |
| euler-preprocess | 3.14.0 | `/srv/ao/workspaces/admin/euler-preprocess-worktrees/streamline-phase-2` | `7d79ec2` |

Loading's complete tracked and untracked Phase 1 changes were copied from
`/srv/ao/workspaces/admin/euler-loading-worktrees/streamline-phase-1` before
implementation. That original worktree remains available and was not reset or
edited. Loading main alone was not used as the implementation baseline.
Contract main was not edited; the assigned contract worktree's pre-existing
`package-lock.json` change was preserved.

The unchanged evaluator at `/srv/ao/workspaces/admin/euler-eval`, commit
`7e445fb`, was included only in opt-in compatibility checks.

## Test results

The affected package suites use the actual modified sources:

| Suite | Result |
|---|---|
| Contract | **323 passed** |
| Loading | **565 passed**, 15 real-dataset cases deselected; 11 existing Pillow warnings |
| Crawler | **116 passed** |
| Preprocess | **180 passed**, 2 existing skips (MPS unavailable and fog dataset unconfigured) |

The opt-in shared real-consumer matrix reports:

| Target | Passed | Strict expected failures |
|---|---:|---:|
| Crawler contract conformance | 88 | 0 |
| Loading compatibility | 22 | 2 |
| Preprocess compatibility | 6 | 0 |
| Evaluator compatibility | 13 | 1 |
| New five-field materialization integration | 2 | 0 |
| **Total** | **131** | **3** |

The three retained expected failures are the VKITTI and generic dense-depth
loaders ignoring declared depth scale, and evaluator center-crop origin inference.
The former legacy skew xfail is deliberately resolved by shared `C @ R @ K`
geometry and now asserts the correct projection. The preprocessing-builder check
now asserts the requested center-crop pixels, because the builder consumes the
shared configuration.

The new checks cover real source files and producer APIs: five-field
480×960 → 384×768 → 320×640 generation, known depth probe **2.981375**, calibrated
K, exact NPY and quantized PNG reload, explicit replay, typed calibration views,
changed IDs, multiple sensors, variants and variable sizes, repeated/spawned
access, source immutability, and a second crop of materialized output. Persistence
checks cover directory/ZIP/scopes, physical and inline splits, relocated sidecars,
identical artifact bytes with distinct IDs, failed encoders, partial writes,
interrupted publication, resume/conflicts, corrupt or missing records, stale
metadata fallback, and source bytes changed before publication.

Contract and crawler full Ruff checks pass. Loading and preprocess have existing
repository-wide lint findings (also present in their baselines); Phase 2 modules
and tests pass Ruff. Existing unrelated lint issues were not used to loosen
checks. Both available lockfiles pass `uv lock --check`. Generated schemas,
Phase 1 and Phase 2 vectors, and the 90-declaration legacy loader observation
snapshot pass their `--check` commands.

## Distribution checks

All four packages build both wheel and source archive under each worktree's
`dist/phase2/`; all **eight** archives pass `twine check --strict`. The contract
and crawler distribution verifier scripts pass. Archive inspection confirms the
new modules, fixtures, schemas, source tests, documentation and producer example
are shipped as appropriate, with no source-path dependency URLs in wheel metadata.

All four wheels were installed without source overrides into
`/tmp/euler-phase2-wheel-check`. Imports were asserted to resolve inside that
environment, not into worktrees. Its two shared directory/ZIP materialization
checks pass using the wheel's shipped fixtures. The installed `euler-preprocess
spatial` CLI also passes a five-field export/reload check with relative config
paths, changed IDs, scoped ZIPs and sidecar receipts.

Before adding scientific dependencies, the contract wheel imported, loaded its
packaged Phase 2 vector and validated a materialized receipt without NumPy,
Torch, Pillow, pytest or jsonschema installed. Runtime dependencies remain zero.

## Reproduction

The consumer runs used NumPy 2.4.6, Torch 2.12.1, Pillow 12.2.0, pytest 9.1.1
and OpenCV headless 5.0.0.93. The isolated loading worktree's `.venv` has all four
packages installed editable, with existing local scientific dependencies reused.
Package suites were run separately to avoid collisions between their `tests`
packages, with `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`.

From the contract worktree:

```sh
uv run pytest -q
uv lock --check
uv run ruff check .
uv run python scripts/generate_schemas.py --check
uv run python scripts/generate_phase1_fixture.py --check
uv run python scripts/generate_phase2_fixture.py --check
uv run python scripts/refresh_loader_observations.py \
  /srv/ao/workspaces/admin/euler-loading-worktrees/streamline-phase-2 --check

OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run python scripts/check_ecosystem.py \
  --repositories /srv/ao/workspaces/admin \
  --repository euler-loading=/srv/ao/workspaces/admin/euler-loading-worktrees/streamline-phase-2 \
  --repository ds-crawler=/srv/ao/workspaces/admin/ds-crawler-worktrees/streamline-phase-2 \
  --repository euler-preprocess=/srv/ao/workspaces/admin/euler-preprocess-worktrees/streamline-phase-2 \
  --python /srv/ao/workspaces/admin/euler-loading-worktrees/streamline-phase-2/.venv/bin/python \
  --report /tmp/phase2-ecosystem-results.json
```

For a separate consumer environment, install all four local source trees or all
four built wheels together so dependency resolution does not select older
published companions. For example, after running `uv build --out-dir dist/phase2`
in each worktree:

```sh
uv venv /tmp/euler-phase2-consumer --python 3.11
uv pip install --python /tmp/euler-phase2-consumer/bin/python \
  torch \
  /srv/ao/workspaces/admin/euler-dataset-contract-worktrees/streamline-phase-2/dist/phase2/*.whl \
  /srv/ao/workspaces/admin/ds-crawler-worktrees/streamline-phase-2/dist/phase2/*.whl \
  /srv/ao/workspaces/admin/euler-loading-worktrees/streamline-phase-2/dist/phase2/*.whl \
  /srv/ao/workspaces/admin/euler-preprocess-worktrees/streamline-phase-2/dist/phase2/*.whl
```

Torch supplies the default CPU execution profile; this command does not require
CUDA execution. A supported `pillow_cpu` binding can be used without Torch.

Crawler's development lock uses a sibling contract path; in this workspace the
untracked external symlink
`/srv/ao/workspaces/admin/ds-crawler-worktrees/euler-dataset-contract` resolves to
the assigned contract worktree. This development override is not a wheel runtime
dependency. Release dependency order is contract → crawler → loading → preprocess.

## Limits

Only Python 3.11.2 was available for execution; other interpreters allowed by the
package metadata were not run. CPU profiles are tested; no GPU equivalence or
real-dataset/benchmark accuracy is claimed. Strict exports verify source content
and pinned decoder/backend profiles, and may replay during writing and
finalization. Metadata-only or unverified snapshot assertions cannot create
strict materialization claims. Revision names remain author assertions.

Publication requires one writer per output. ZIP resume is unsupported; multiple
logical output roots are finalized independently. The new generation layout
requires the matching crawler reader. Full derivation-graph traversal, evaluator
preflight/pairing, and migration away from dimension heuristics remain Phase 3.

See [the Phase 2 wire and runtime contract](phase2.md), loading
`docs/materialization.md`, preprocess `docs/spatial.md`, and crawler
`docs/validated-publication.md` for the public APIs and opt-in producer config.
