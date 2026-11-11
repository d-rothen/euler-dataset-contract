"""Command line: ``python -m euler_dataset_contract <command>``.

``inventory``
    Print :func:`euler_dataset_contract.report.modality_report` as JSON: the
    modality inventory, the registered ``modality.meta`` schema, and the
    installed version. euler-view's cluster compatibility check runs this in a
    cluster environment.

``resolve KEY [KEY ...]``
    Print how each persisted modality key resolves (canonical id, status,
    diagnostics).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .modalities import resolve_modality
from .report import modality_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m euler_dataset_contract",
        description="Inspect the Euler dataset contract installed here.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    inventory = commands.add_parser(
        "inventory", help="Print the modality vocabulary report as JSON."
    )
    inventory.add_argument(
        "--no-meta-schema",
        action="store_true",
        help="Leave out the registered modality.meta schema.",
    )
    inventory.add_argument(
        "--indent", type=int, default=None, help="Indent the JSON output."
    )

    resolve = commands.add_parser(
        "resolve", help="Resolve persisted modality keys to canonical ids."
    )
    resolve.add_argument("keys", nargs="+", metavar="KEY")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "inventory":
        payload = modality_report(include_meta_schema=not args.no_meta_schema)
        json.dump(payload, sys.stdout, indent=args.indent, sort_keys=False)
        sys.stdout.write("\n")
        return 0

    results = {}
    for key in args.keys:
        resolution = resolve_modality(key)
        results[key] = {
            "modality_id": resolution.modality_id,
            "candidate_id": resolution.candidate_id,
            "status": resolution.status,
            "diagnostics": list(resolution.diagnostics),
        }
    json.dump(results, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
