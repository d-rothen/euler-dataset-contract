"""Generate the checked-in JSON Schema artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from euler_dataset_contract import build_dataset_head_schema, build_meta_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


def _render(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def _schemas() -> dict[str, dict]:
    dataset_head = build_dataset_head_schema()
    dataset_head = {
        "$schema": dataset_head.pop("$schema"),
        "$id": (
            "https://raw.githubusercontent.com/d-rothen/euler-dataset-contract/"
            "main/schemas/dataset-head-1.0.schema.json"
        ),
        **dataset_head,
    }
    modality_meta = build_meta_schema()
    modality_meta = {
        "$schema": modality_meta.pop("$schema"),
        "$id": (
            "https://raw.githubusercontent.com/d-rothen/euler-dataset-contract/"
            "main/schemas/modality-meta-1.0.schema.json"
        ),
        **modality_meta,
    }
    return {
        "dataset-head-1.0.schema.json": dataset_head,
        "modality-meta-1.0.schema.json": modality_meta,
    }


def generate(*, check: bool) -> None:
    stale: list[str] = []
    for filename, schema in _schemas().items():
        path = SCHEMA_DIR / filename
        rendered = _render(schema)
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != rendered:
                stale.append(str(path.relative_to(ROOT)))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")

    if stale:
        joined = ", ".join(stale)
        raise SystemExit(
            f"Generated schemas are stale: {joined}. "
            "Run `python scripts/generate_schemas.py`."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when checked-in schemas differ instead of writing them",
    )
    args = parser.parse_args()
    generate(check=args.check)


if __name__ == "__main__":
    main()
