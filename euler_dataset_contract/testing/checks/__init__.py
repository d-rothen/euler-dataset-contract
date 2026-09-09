"""Opt-in Phase 0 checks executed in consumer environments.

These modules intentionally are not collected by this repository's default
unit suite. Run a named module with pytest --pyargs, or use the checkout runner
in scripts/check_ecosystem.py. Missing consumer dependencies are errors, not
silently skipped evidence. Importing this package itself loads no consumers.
"""
