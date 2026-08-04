# Security policy

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities in a public issue.

Use [GitHub's private vulnerability reporting
form](https://github.com/d-rothen/euler-dataset-contract/security/advisories/new)
and include the affected version, impact, reproduction steps, and any suggested
mitigation. Remove credentials, private dataset contents, absolute paths, and
sensitive metadata unless they are strictly necessary to reproduce the issue.

You should receive an acknowledgement after a maintainer reviews the report.
Release timing and disclosure will be coordinated according to severity and
the availability of a safe fix.

## Scope notes

This package parses in-memory Python mappings and generates JSON Schema. It
does not read datasets or execute addon contents. Reports involving archive or
filesystem handling usually belong to `ds-crawler` or `euler-loading`; when in
doubt, report privately here and the maintainers can route it.
