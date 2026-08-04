# Contributing

Thanks for improving `euler-dataset-contract`. Because this package is a shared
boundary, small validation changes can affect several repositories. Focused
changes with fixtures and migration notes are the easiest to review safely.

## Development setup

The project supports Python 3.9 and newer and uses
[`uv`](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/d-rothen/euler-dataset-contract.git
cd euler-dataset-contract
uv sync --extra dev
```

## Before opening a pull request

Run the same checks as CI:

```bash
uv lock --check
uv run ruff check .
uv run pytest
uv run python scripts/generate_schemas.py --check
uv build
uv run python scripts/verify_distribution.py dist/*
uvx twine check dist/*
```

Include a regression test for behavior changes and update the README or docs
for public API or semantic changes. Do not commit dataset archives, generated
build output, credentials, private dataset metadata, or machine-local paths.

## Changing the contract

The package version and serialized contract version solve different problems:

- patch or minor package releases may fix implementation, tests, typing, and
  documentation while continuing to read/write contract `1.0`;
- a serialized contract version changes when persisted semantics or required
  structure become incompatible.

When changing a core field or built-in modality definition:

1. state whether existing heads remain valid;
2. add runtime validation tests and Draft 2020-12 schema tests;
3. run `uv run python scripts/generate_schemas.py` and commit the generated
   schema changes;
4. check the producer path in `ds-crawler` and the consumer paths in
   `euler-loading` and `euler-eval`;
5. document deprecation and migration behavior for any changed meaning.

New package-specific fields normally belong in a versioned addon validator.
New modality metadata should remain JSON-serializable and should not encode a
particular Python array library or loader implementation.

## Reporting issues

Open a GitHub issue with the smallest redacted dataset head that reproduces the
problem, the expected result, the exception, and the package/Python versions.
For a schema mismatch, include whether runtime parsing, JSON Schema validation,
or both produced the result.

Security issues use the private process in [SECURITY.md](SECURITY.md).

## Releasing

1. Set the package version in `pyproject.toml`, update `CHANGELOG.md`, and run
   `uv lock`.
2. Run every check in the pre-PR block above from a clean checkout.
3. Commit the release preparation.
4. Create a `v<package-version>` tag, for example `v0.3.0`, and push it.

The trusted-publishing workflow verifies that the tag matches the project
version, rebuilds and checks both distributions, and then publishes to PyPI.
