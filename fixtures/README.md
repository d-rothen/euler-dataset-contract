# Conformance fixture corpus

The `descriptors` manifest section carries Phase 1 planned addon examples,
canonical encoding/hash vectors, and graph/structural rejection edits. A full
planned head is included in the ordinary valid/canonical suites so old producer
readers must preserve it. See [Phase 1](../docs/phase1.md) for their interpretation.

This directory is the cross-repository source of truth for what a valid
`dataset-head.json` is, what an invalid one fails with, and which modality
identity each legacy modality name resolves to.

Consumer repositories can assert against these exact files. The opt-in Phase 0
checks exercise four consumer packages against the same corpus. Python consumers
get the corpus from the
`euler_dataset_contract.testing` pytest plugin; non-Python consumers such as
`euler-view` read the JSON directly.

The files are data. They contain no Python, no test framework assumptions, and
no repository-local paths.

## Layout

| Path | Contents |
|---|---|
| `index.json` | Manifest of every case. Enumerate the corpus from here. |
| `heads/valid/<name>.json` | A dataset head exactly as a producer would write it. |
| `heads/canonical/<name>.json` | The expected result of parsing the matching valid head and serializing it again. |
| `heads/invalid/<name>.json` | One rejection case: a head plus the error it must produce. |
| `inventory/` | Vendored vocabularies used to detect drift against other repositories. |
| `preprocessing/` | Two five-field resize/crop examples, backend and invalid-depth observations. |
| `geometry/` | Independent camera/projection references and known metric depth/XYZ values. |
| `calibration/` | Current hierarchical selection and source-immutability probes. |
| `alignment/` | Evaluator shape heuristics and reference crop-origin counterexample. |
| `decoding/` | Known raw arrays with expected scaling, dtypes, layouts, and label/cloud representations. |
| `persistence/` | Opaque addon and variant-origin probes, storage scopes, and stale output metadata. |

The manifest contains 19 valid heads, 19 invalid cases, three inventories, and
ten evidence cases. `phase0-*` heads are synthetic metadata examples; none
asserts that a real dataset or built-in loader uses that exact encoding.

## The three assertions

A conforming implementation satisfies all three.

**Valid heads parse.** Reading `heads/valid/<name>.json` and parsing it
succeeds.

**Parsing is canonical and idempotent.** Serializing the parsed head equals
`heads/canonical/<name>.json` byte-for-byte after JSON decoding, and parsing
that canonical form again yields the same mapping. This is what pins
normalization: `heads/valid/rgb-file-types-camel-case.json` authors
`fileTypes: [".PNG", " jpg "]` and its canonical file records
`file_types: ["jpg", "png"]`.

**Invalid heads are rejected with the stated error.** Each invalid case is an
envelope rather than a bare head:

```json
{
  "description": "Contract versions are numeric major.minor or major.minor.patch.",
  "expected_exception": "ValueError",
  "expected_error": "dataset_head.contract.version must look like",
  "head": {"contract": {"kind": "dataset_head", "version": "v1.0"}}
}
```

`expected_error` is a **substring** of the raised message, not the whole
message, so wording may be improved without breaking every consumer. It is the
message produced when the head is parsed with the default context
`dataset_head`; a consumer that passes its own context asserts against the part
of the substring that follows the context prefix.

`schema_valid` defaults to `false`. The two existing rejection cases accepted
by the current JSON Schema set it to `true` and give a `schema_note`. This
records a discrepancy without changing the runtime acceptance contract.

Evidence payloads use `contract.kind: phase0_evidence` and carry their own
`name`, `kind`, and description. Their `reference`/`observed` answers are test
data, not executable transform descriptors. `phase0_annotations` and
`phase0_origin` are deliberately opaque preservation probes, with no replay or
materialization claim. See [Phase 0 evidence](../docs/phase0-evidence.md).

## Index metadata

`index.json` carries the description of each case and, for valid heads, a
`covers` list stating what the case exists to protect. Enumerating from the
manifest rather than by globbing means a consumer that has an outdated copy of
the corpus fails on the missing file instead of quietly testing less than it
believes.

## Inventory

`inventory/euler-loading-modality-types.json` is a vendored copy of the
modality vocabulary `euler-loading` emits from its generated `loaders.json`,
recorded with the source path and a content hash. It exists so that
`euler-dataset-contract` can assert that every emitted modality type resolves
through the shipped modality inventory
(`euler_dataset_contract/data/modality-inventory-1.0.json`) without taking a
dependency on `euler-loading`. Refresh it when `loaders.json` changes; the
drift test then names any type that has no inventory entry.

`inventory/dataset-modality-types.json` records the operator's exact 14 names,
including the clarification that `spectral_map` was never used and
`spherical_map` is homogeneous ray directions. `inventory/loader-observations.json`
captures 90 CPU/Torch declarations and their source hashes independently of the
reported dataset list. Capture it without importing array libraries:

```bash
python scripts/refresh_loader_observations.py /path/to/euler-loading --check
```

Run from the repository root; omit `--check` to refresh both loader inventories
after reviewing source changes. Numerical checks separately verify selected
declarations against actual synthetic encoded bytes.

## Changing the corpus

Adding a case is additive and safe. Changing or removing one is a contract
change: it means some repository's current behaviour is now wrong, so land it
together with the follow-up in the repositories that assert against it. See
[docs/conformance-fixtures.md](../docs/conformance-fixtures.md) for the
consumer wiring and the rule that governs contract changes.
