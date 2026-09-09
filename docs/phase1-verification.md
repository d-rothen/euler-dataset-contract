# Phase 1 verification

The contract 0.4.0 and loading 2.23.0 source changes implement the revised
[Phase 1 scope](phase1.md). This records local verification, not publication.

The subsequent [Phase 0/1 review and amendments](phase0-1-review.md) correct five
issues and record the latest run: 309 contract tests, 545 loading tests, and
128 compatibility tests passed, with the same four legacy expected failures.
The original Phase 1 verification record follows for comparison.

The contract worktree started exactly at Phase 0 commit `c6c8cd4`. The isolated
loading worktree started at `f3db6ff`. Crawler `340c228`, preprocess `7d79ec2`,
eval `7e445fb`, and the shared loading checkout remained unchanged. Both changed
repositories use branch `streamline-phase-1`; the pre-existing contract
`package-lock.json` modification was preserved.

## Results

| Check | Result |
|---|---|
| Contract unit/data/schema/plugin/distribution suite | 286 passed |
| Loading complete unit suite | 514 passed; 15 real-dataset tests deselected |
| Loading descriptor suite, included above | 63 passed, including spawned workers and pickled plans |
| Crawler compatibility suite | 88 passed |
| Loading compatibility suite | 21 passed; 3 strict expected failures retained |
| Preprocess compatibility suite | 6 passed |
| Eval compatibility suite | 13 passed; 1 strict expected failure retained |
| Contract lock, Ruff, generated schemas, generated descriptor/vector check | Passed |
| Contract wheel/sdist build, fixture/schema distribution verification, Twine | Passed |
| Loading wheel/sdist build and Twine | Passed |
| Installed contract wheel outside source, no optional dependencies | Profiles, descriptors, hashes, schemas, all 20 golden heads, and strict addon rejection passed |
| Installed contract/loading wheels with Torch imports blocked | Explicit Pillow five-field execution passed |
| Original Phase 0 core plus unchanged crawler | New addons preserved through directory/ZIP and root/scoped persistence |

The environment was Linux/Python 3.11.2, pytest 9.1.1, NumPy 2.4.6, Torch
2.12.1 (`torch.__version__` includes `+cu130`), Pillow 12.2.0, JSON Schema
4.26.0 for development checks, and OpenCV headless 5.0.0.93 for consumer checks.
All tensor execution was on CPU. The standalone contract wheel environment
contained no NumPy, Torch, Pillow, pytest, or JSON Schema engine.

The four expected failures remain the legacy loading skew helper, two loaders'
head-scale behavior, and eval's center-crop alignment guess. No baseline assertion
was weakened to accommodate the opt-in executor. The new path separately proves
correct skew/projection geometry, ordered resize/crop, backend-specific samples,
validity-aware depth, exact restoration of float64 sentinels, explicit layouts,
and source immutability. Loading's existing Pillow deprecation warnings remain.

## Reproduction

Run the contract checks listed in `CONTRIBUTING.md`, plus:

```bash
uv run python scripts/generate_phase1_fixture.py --check
uv run python scripts/check_ecosystem.py \
  --repositories /path/to/checkouts \
  --repository euler-loading=/path/to/loading-worktree \
  --python /path/to/consumer-python --report /tmp/phase1-results.json
```

For loading, put the intended contract/loading/crawler source roots first on
`PYTHONPATH` and run its `pytest` suite from its worktree. Its development extra
includes JSON Schema for conformance tests; runtime validation uses the contract's
dependency-free definitions. Execution tests pin the installed backend profile
instead of assuming every test environment matches the shared vector's capture
versions.

The original-reader check used a temporary export of the contract package at
`c6c8cd4`, confirmed its import origin, and wrote/read the new canonical head
through the unchanged crawler. Installed-wheel checks ran outside both source
trees and confirmed installed import origins.

These synthetic checks do not establish real dataset conformance, CUDA parity,
per-sample receipt capture, materialized writer metadata, hierarchy-aware output
calibration, producer wiring, or GT replay. Those latter integrations remain
Phase 2/3 and are not asserted by `state: "planned"`.
