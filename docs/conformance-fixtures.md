# Conformance fixtures

`euler-dataset-contract` sits under every other package in the ecosystem, so a
change to it can pass here and break `euler-loading`, `euler-eval`, or
`ds-crawler` a release later. The conformance corpus closes that gap: one set of
data files, asserted against by every repository, so a disagreement about what
the contract means surfaces in CI rather than in a dataset.

This document describes the corpus, how a repository wires it in, and the rule
that governs contract changes.

## What ships

| Artifact | Location in a checkout | Location in a wheel |
|---|---|---|
| Conformance corpus | `fixtures/` | `euler_dataset_contract/_fixtures/` |
| Modality inventory | `euler_dataset_contract/data/modality-inventory-1.0.json` | same |
| Pytest plugin | `euler_dataset_contract/testing/` | same |

The corpus is authored at the repository root because it is not Python. A
non-Python consumer such as `euler-view` reads the JSON directly from a
checkout or from the source distribution. A wheel has no repository root, so
the build copies the corpus into the package; `fixtures_root()` prefers the
packaged copy and falls back to the checkout, which is what makes an editable
install read the working tree.

Both locations are asserted by `scripts/verify_distribution.py`, because a
silently missing data file would break every consumer at once.

## The corpus

[`fixtures/README.md`](../fixtures/README.md) documents the layout in full. In
short, `fixtures/index.json` lists every case, valid heads are stored exactly
as a producer would write them, each has a canonical file recording the result
of parsing and re-serializing it, and each invalid case pairs a head with a
substring of the error it must produce.

Three assertions define conformance:

1. every valid head parses;
2. serializing the parsed head equals its canonical file, and parsing that
   canonical form again changes nothing;
3. every invalid head is rejected with the stated error.

The second is what pins normalization. `fileTypes` becomes `file_types`,
extensions are lowercased, stripped of a leading dot, and sorted — and the
canonical file states the result rather than a test asserting it in one
repository and not another.

## Wiring a repository in

The corpus and the plugin exist; connecting the seven Python repositories in
section 4.1 of the plan is a per-repository follow-up, because each asserts
something different against the same heads.

Add the testing extra to the development dependencies:

```toml
[project.optional-dependencies]
dev = [
  "euler-dataset-contract[testing]",
  "pytest",
]
```

The extra carries `pytest` and nothing else. The core package keeps no runtime
dependencies, and importing `euler_dataset_contract` never imports pytest.

The plugin registers through the `pytest11` entry point, so there is no
`conftest.py` to write. A repository asserts against the corpus like this:

```python
def test_contract_heads_parse(golden_head, assert_head_roundtrip):
    assert_head_roundtrip(golden_head.head)


def test_contract_heads_are_rejected(invalid_head):
    with pytest.raises(ValueError) as excinfo:
        parse_dataset_head(invalid_head.head)
    assert invalid_head.expected_error in str(excinfo.value)
```

Two functions become one test per case. When the contract adds a case, the
repository runs it on its next `uv sync` without editing a test.

The more useful form for a consumer is to run its own reader over the same
heads: `ds-crawler` asserts that it can write them, `euler-loading` that it can
resolve a loader for each, `euler-eval` that it accepts what it claims to.

### What the plugin provides

| Name | Kind | Contents |
|---|---|---|
| `golden_head` | parametrized argument | One valid case per test run, id'd by case name. |
| `invalid_head` | parametrized argument | One rejection case per test run. |
| `golden_heads` | session fixture | Every valid case, in manifest order. |
| `invalid_heads` | session fixture | Every rejection case, each with `expected_error`. |
| `modality_inventory` | session fixture | The shipped modality inventory. |
| `vendored_modality_types` | session fixture | The vocabulary `euler-loading` emits today. |
| `fixture_index` | session fixture | The corpus manifest. |
| `conformance_fixtures_root` | session fixture | Filesystem root of the corpus. |
| `assert_head_roundtrip` | session fixture | Callable asserting a head parses to a stable, idempotent mapping. |

`golden_head` and `invalid_head` are reserved argument names: a test that takes
either one is parametrized by the plugin, so do not define a local fixture with
those names.

Outside a pytest run the same values are plain functions:

```python
from euler_dataset_contract.testing import golden_heads, modality_inventory
```

That layer imports no test framework, so a script or a non-pytest test runner
can use it. Importing the plugin without pytest installed raises an
`ImportError` naming the extra to install.

## The rule

**A contract change must be proven against these fixtures in every repository
that reads heads, before it ships.**

Concretely, changing validation, normalization, or the modality inventory
means:

1. add or change the corpus case that demonstrates the new behaviour, in the
   same commit as the code;
2. run this repository's suite;
3. run the suite of every repository in section 4.1 of the
   [ecosystem streamlining plan](ecosystem-streamlining-plan.md) that reads
   dataset heads, against the changed corpus;
4. land the consumer changes any of them need before releasing.

Adding a case is additive: a consumer that has not updated yet is unaffected
until it does. Changing or removing a case is not, because it asserts that some
repository's current behaviour is now wrong. Those land together.

## The modality inventory

`euler_dataset_contract/data/modality-inventory-1.0.json` records the modality
identities the ecosystem emits today, the legacy names that resolve to them,
and the two names that are not modalities at all. It encodes section 5.3 of the
plan.

In phase 0 it is **data only**. No parsing, validation, or schema generation
reads it, and `modality.key` behaves exactly as it did before. It exists so
that the registry built in phase 1 starts from a reviewed inventory rather than
from a fresh reading of six loaders.

Two properties of the file are worth knowing when reading it:

- Entries whose mapping depends on an unanswered question in section 12 of the
  plan carry `"status": "provisional"` and a note naming the question. They are
  a record of what is not yet decided, not a decision.
- Aliases are objects rather than bare strings, so one lookup yields the
  canonical id together with the status, the provenance of the legacy name, and
  any representation values the name implies. Phase 4's deprecation windows have
  somewhere to live without a second structure.

`fixtures/inventory/euler-loading-modality-types.json` is a vendored copy of
what `euler-loading` emits, so `tests/test_modality_inventory.py` can prove that
every emitted type resolves to exactly one identity without this package
depending on that one. Refresh it when `loaders.json` changes; the test then
names anything unclassified.
