"""Generate a data-only Phase 2 wire vector. Label hashes are synthetic, not IO evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from euler_dataset_contract import (
    ArtifactReceipt,
    ExecutionReceipt,
    MaterializedTransforms,
    OutputPlan,
    TransformsAddon,
    bound_derivation_digest,
    canonical_digest,
    receipt_location,
    validate_artifact_receipt,
)

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    descriptor = json.loads(
        (ROOT / "fixtures/descriptors/five-field.json").read_text()
    )["addon"]
    for name, source in descriptor["sources"].items():
        source["verification"] = "content"
        source["content_digest"] = canonical_digest({"synthetic_manifest": name})
    descriptor = TransformsAddon(descriptor)
    recipe = descriptor["recipe"]
    input_shapes = {
        name: binding["profile"]["shape"] for name, binding in recipe["fields"].items()
    }
    output_shapes = {
        name: [3, 3]
        if name == "intrinsics"
        else [320, 640, 3]
        if name in ("rgb", "ray_map")
        else [320, 640]
        for name in input_shapes
    }
    source_ids = {
        name: "/scene_01/camera_0/calibration"
        if name == "source_intrinsics"
        else "/scene_01/camera_0/frame_0"
        for name in descriptor["sources"]
    }
    operations = [
        dict(
            id=op["id"],
            op=op["op"],
            version="1.0",
            status="executed",
            reason="applied",
            input_size=source_size,
            output_size=size,
            offset=offset,
            image_transform=matrix,
        )
        for op, source_size, size, offset, matrix in zip(
            recipe["operations"],
            [[480, 960], [384, 768]],
            [[384, 768], [320, 640]],
            [None, [32, 64]],
            [
                [[0.8, 0, (0.8 - 1) / 2], [0, 0.8, (0.8 - 1) / 2], [0, 0, 1]],
                [[1, 0, -64], [0, 1, -32], [0, 0, 1]],
            ],
        )
    ]
    execution = ExecutionReceipt(
        dict(
            version="2.0",
            recipe_digest=descriptor["recipe_digest"],
            bound_digest=bound_derivation_digest(descriptor, source_ids),
            source_full_ids=source_ids,
            source_content={
                name: canonical_digest({"synthetic_file": name}) for name in source_ids
            },
            input_digests={
                name: canonical_digest({"synthetic_input": name})
                for name in input_shapes
            },
            output_digests={
                name: canonical_digest({"synthetic_output": name})
                for name in output_shapes
            },
            input_shapes=input_shapes,
            output_shapes=output_shapes,
            operations=operations,
            execution=recipe["execution"],
            verification="content",
        )
    )
    profile = deepcopy(recipe["fields"]["rgb"]["profile"])
    profile["shape"] = [320, 640, 3]
    profile["image_plane"] = "synthetic_output"
    profiles = {"default": {"decoded": profile, "storage": profile}}
    plan = OutputPlan(
        dict(
            version="2.0",
            dataset_id="derived_rgb",
            revision="synthetic_v1",
            modality_key="rgb",
            field="rgb",
            metadata_scope=".",
            encoding=dict(
                id="npy",
                version="1.0",
                scale=1,
                range=[-9007199254740991, 9007199254740991],
                rounding="ties_to_even",
                clipping="reject",
                versions={"numpy": "2.4.6"},
            ),
            profiles=profiles,
            dependencies={"default": ["rgb", "intrinsics"]},
            variants={"default": descriptor.to_dict()},
        )
    )
    receipt = ArtifactReceipt(
        dict(
            version="2.0",
            plan_digest=canonical_digest(plan.to_dict()),
            variant_id="default",
            output_full_id="/changed/frame_0",
            execution=execution.to_dict(),
            artifact=dict(
                digest="sha256:" + hashlib.sha256(b"synthetic-artifact").hexdigest(),
                decoded_digest=execution["output_digests"]["rgb"],
                decoded=profile,
                storage=profile,
            ),
        )
    )
    validate_artifact_receipt(receipt, plan)
    location, records = receipt_location(receipt, sidecar=True)
    inline, _ = receipt_location(receipt)
    tree = {
        "children": {
            "changed": {
                "files": [
                    {
                        "id": "frame_0",
                        "path": "sample.npy",
                        "attributes": {"euler_transforms": inline},
                    }
                ]
            }
        }
    }
    addon = MaterializedTransforms(
        dict(
            version="2.0",
            state="materialized",
            plan=plan.to_dict(),
            plan_digest=canonical_digest(plan.to_dict()),
            required_features=[
                "receipts.bound",
                "artifacts.sha256",
                "calibration.views",
            ],
            mapping=dict(
                mode="explicit",
                count=1,
                index_digest=canonical_digest(tree),
                receipts="per_file",
            ),
        )
    )
    return dict(
        name="phase2-five-field",
        description="Synthetic wire assertions only. Recipe/plan/receipt digests are computed; source/array label hashes are not independently checked content. Real IO conformance uses the shared analytic corpus through consumer APIs.",
        descriptor=descriptor.to_dict(),
        execution=execution.to_dict(),
        plan=plan.to_dict(),
        receipt=receipt.to_dict(),
        inline=inline,
        sidecar=location,
        records=records,
        addon=addon.to_dict(),
        index=tree,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "fixtures/descriptors/phase2-five-field.json"
    rendered = json.dumps(fixture(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not path.exists() or path.read_text() != rendered:
            raise SystemExit(
                "Phase 2 fixture is stale; run scripts/generate_phase2_fixture.py"
            )
    else:
        path.write_text(rendered)


if __name__ == "__main__":
    main()
