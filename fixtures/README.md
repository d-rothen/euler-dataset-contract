# Conformance fixture corpus

This directory is the cross-repository source of truth for what a valid
`dataset-head.json` is, what an invalid one fails with, and which modality
identity each legacy modality name resolves to.

Every repository in the ecosystem asserts against these exact files. A contract
change that a repository cannot satisfy is visible in that repository's CI
before it ships, rather than after. Python consumers get the corpus from the
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

## Changing the corpus

Adding a case is additive and safe. Changing or removing one is a contract
change: it means some repository's current behaviour is now wrong, so land it
together with the follow-up in the repositories that assert against it. See
[docs/conformance-fixtures.md](../docs/conformance-fixtures.md) for the
consumer wiring and the rule that governs contract changes.
