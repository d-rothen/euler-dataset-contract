# Changelog

All notable changes to this project are documented here. Package releases use
semantic versioning independently of the serialized dataset contract version.

## [0.3.0] - 2026-08-04

### Added

- Public package metadata, MIT license, contribution and security policies.
- A complete contract reference and ecosystem-informed future-directions
  document.
- Checked-in Draft 2020-12 schemas and distribution verification tooling.
- CI across all supported Python versions and a guarded trusted-publishing
  workflow.
- A `py.typed` marker for typed consumers.

### Changed

- Dataset-head JSON Schema now selects metadata requirements from
  `modality.key`, matching runtime validation.
- Core structures reject unknown keys consistently with the JSON Schema.
- Contract versions must be explicit in serialized heads.
- Boolean values are no longer accepted where numeric metadata is required.
- Modality registration validates registry keys and keeps the legacy exported
  registry view synchronized.

## [0.2.2] - 2026-07-18

- Kept evaluated type aliases importable on Python 3.9.

## [0.2.0] - 2026-03-30

- Added structured dataset-head parsing, modality metadata registration,
  addon validators, and JSON Schema generation.

[0.3.0]: https://github.com/d-rothen/euler-dataset-contract/compare/v0.2.0...HEAD
[0.2.2]: https://pypi.org/project/euler-dataset-contract/0.2.2/
[0.2.0]: https://github.com/d-rothen/euler-dataset-contract/releases/tag/v0.2.0
