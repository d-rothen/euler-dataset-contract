"""Run the opt-in ecosystem consumer checks against local source checkouts.

Use a Python environment containing the selected consumers' dependencies.
This script neither installs packages nor changes the consumer repositories.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "crawler": ("ds-crawler",),
    "loading": ("ds-crawler", "euler-loading"),
    "preprocess": ("ds-crawler", "euler-loading", "euler-preprocess"),
    "eval": ("ds-crawler", "euler-loading", "euler-eval"),
    "materialization": ("ds-crawler", "euler-loading", "euler-preprocess"),
}


def source_state(root: Path) -> dict[str, object]:
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain"], text=True
    )
    return {"commit": commit, "dirty": bool(status)}


def test_results(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"error": "pytest did not produce a report"}
    result: dict[str, object] = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "expected_failures": [],
    }
    for case in ET.parse(path).getroot().iter("testcase"):
        skip = case.find("skipped")
        if case.find("failure") is not None:
            status = "failed"
        elif case.find("error") is not None:
            status = "errors"
        elif skip is not None and skip.get("type") == "pytest.xfail":
            status = "xfailed"
            result["expected_failures"].append(
                {
                    "test": case.get("name"),
                    "reason": skip.get("message"),
                }
            )
        elif skip is not None:
            status = "skipped"
        else:
            status = "passed"
        result[status] += 1
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repositories",
        type=Path,
        required=True,
        help="Parent of the ds-crawler/euler-* source checkouts",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python with pytest and consumer dependencies installed",
    )
    parser.add_argument(
        "--repository", action="append", default=[], metavar="NAME=PATH",
        help="Override a named source checkout (repeat for isolated worktrees)",
    )
    parser.add_argument(
        "--target",
        choices=tuple(TARGETS),
        action="append",
        help="Repeat to select consumers; default: all five",
    )
    parser.add_argument("--report", type=Path, help="Write a JSON execution report")
    args = parser.parse_args()
    targets = list(dict.fromkeys(args.target or TARGETS))
    names = sorted({name for target in targets for name in TARGETS[target]})
    roots = {name: (args.repositories / name).resolve() for name in names}
    for override in args.repository:
        name, separator, path = override.partition("=")
        if not separator or name not in {item for target in TARGETS.values() for item in target}:
            parser.error("--repository requires a supported repository NAME=PATH")
        if name in roots:
            roots[name] = Path(path).resolve()
    for name, path in roots.items():
        if not (path / name.replace("-", "_") / "__init__.py").is_file():
            parser.error(f"Missing {name} source checkout: {path}")

    env = os.environ.copy()
    # Explicit checkouts take precedence over installed/editable distributions.
    paths = [str(ROOT), *(str(path) for path in roots.values())]
    env["PYTHONPATH"] = os.pathsep.join(
        paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    env["PYTEST_ADDOPTS"] = ""
    if "euler-loading" in roots:
        result = subprocess.run(
            [
                args.python,
                str(ROOT / "scripts/refresh_loader_observations.py"),
                str(roots["euler-loading"]),
                "--check",
            ],
            cwd=ROOT,
            env=env,
        )
        if result.returncode:
            return result.returncode

    probe = """
import importlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
roots = json.loads(sys.argv[1])
for name, root in roots.items():
    module = importlib.import_module(name.replace('-', '_'))
    assert Path(module.__file__).resolve().is_relative_to(Path(root)), (name, module.__file__)
packages = {}
for name in ('pytest', 'numpy', 'torch', 'Pillow', 'opencv-python', 'opencv-python-headless'):
    try:
        packages[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        pass
print(json.dumps({'python': platform.python_version(), 'platform': platform.system(), 'packages': packages}))
"""
    checked_roots = {
        "euler-dataset-contract": str(ROOT),
        **{name: str(path) for name, path in roots.items()},
    }
    result = subprocess.run(
        [args.python, "-c", probe, json.dumps(checked_roots)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    report = {
        "scope": "Synthetic Phase 0 and Phase 2 checks; Torch runs on CPU; no CUDA parity claim",
        "environment": json.loads(result.stdout),
        "sources": {name: {"path": path, **source_state(Path(path))}
                    for name, path in checked_roots.items()},
        "checks": {},
    }
    print(
        json.dumps({key: report[key] for key in ("environment", "sources")}, indent=2),
        flush=True,
    )
    failed = False
    with tempfile.TemporaryDirectory(prefix="euler-phase0-") as temporary:
        for target in targets:
            print(f"\nChecking {target}", flush=True)
            xml_path = Path(temporary) / f"{target}.xml"
            result = subprocess.run(
                [
                    args.python,
                    "-m",
                    "pytest",
                    "--pyargs",
                    f"euler_dataset_contract.testing.checks.test_{target}",
                    "-q",
                    "-rx",
                    "--tb=short",
                    f"--junitxml={xml_path}",
                ],
                cwd=ROOT,
                env=env,
            )
            counts = test_results(xml_path)
            report["checks"][target] = {"exit_code": result.returncode, **counts}
            # Missing dependencies fail collection. Unexpected skips also fail the matrix.
            failed |= result.returncode != 0 or bool(counts.get("skipped"))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.report}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
