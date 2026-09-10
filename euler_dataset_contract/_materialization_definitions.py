"""Data-only Phase 2 definitions, shared by runtime validation and schemas."""

from ._descriptor_definitions import (
    DIGEST,
    EXECUTION,
    FEATURES,
    FULL_ID,
    NUMBER,
    OFFSET,
    PROFILE,
    SIZE,
    TEXT,
    TOKEN,
    TRANSFORMS,
    array,
    enum,
    mapping,
    obj,
)

MATRIX = array(array(NUMBER, 3, maxItems=3), 3, maxItems=3)
TRACE_OPERATION = obj(
    {
        "id": TOKEN,
        "op": enum("euler_loading.resize", "euler_loading.crop"),
        "version": enum("1.0"),
        "status": enum("executed", "skipped"),
        "reason": enum("applied", "identity_size"),
        "input_size": SIZE,
        "output_size": SIZE,
        "offset": {"oneOf": [OFFSET, {"type": "null"}]},
        "image_transform": MATRIX,
    },
    (
        "id",
        "op",
        "version",
        "status",
        "reason",
        "input_size",
        "output_size",
        "offset",
        "image_transform",
    ),
)
EXECUTION_RECEIPT = obj(
    {
        "version": enum("2.0"),
        "recipe_digest": DIGEST,
        "bound_digest": DIGEST,
        "source_full_ids": {**mapping(FULL_ID), "maxProperties": 64},
        "source_content": mapping(DIGEST),
        "input_digests": mapping(DIGEST),
        "output_digests": mapping(DIGEST),
        "input_shapes": mapping(
            array({"type": "integer", "minimum": 1}, 2, maxItems=4)
        ),
        "output_shapes": mapping(
            array({"type": "integer", "minimum": 1}, 2, maxItems=4)
        ),
        "operations": array(TRACE_OPERATION, 1, maxItems=128),
        "execution": EXECUTION,
        "verification": enum("content", "metadata"),
    },
    (
        "version",
        "recipe_digest",
        "bound_digest",
        "source_full_ids",
        "source_content",
        "input_digests",
        "output_digests",
        "input_shapes",
        "output_shapes",
        "operations",
        "execution",
        "verification",
    ),
)
ENCODING = obj(
    {
        "id": enum("npy", "png_rgb8", "png_depth16", "png_mask8"),
        "version": enum("1.0"),
        "scale": {"type": "number", "exclusiveMinimum": 0},
        "range": array(NUMBER, 2, maxItems=2),
        "rounding": enum("ties_to_even"),
        "clipping": enum("reject"),
        "versions": mapping(TEXT),
    },
    ("id", "version", "scale", "range", "rounding", "clipping", "versions"),
)
OUTPUT_PLAN = obj(
    {
        "version": enum("2.0"),
        "dataset_id": TOKEN,
        "revision": TEXT,
        "modality_key": TOKEN,
        "field": TOKEN,
        "encoding": ENCODING,
        "metadata_scope": TEXT,
        "dependencies": mapping(array(TOKEN, 1, uniqueItems=True)),
        "profiles": mapping(
            obj({"decoded": PROFILE, "storage": PROFILE}, ("decoded", "storage"))
        ),
        "variants": {**mapping(TRANSFORMS), "maxProperties": 64},
    },
    (
        "version",
        "dataset_id",
        "revision",
        "modality_key",
        "field",
        "encoding",
        "variants",
        "profiles",
        "metadata_scope",
        "dependencies",
    ),
)
ARTIFACT_RECEIPT = obj(
    {
        "version": enum("2.0"),
        "plan_digest": DIGEST,
        "variant_id": TOKEN,
        "output_full_id": FULL_ID,
        "execution": EXECUTION_RECEIPT,
        "artifact": obj(
            {
                "digest": DIGEST,
                "decoded_digest": DIGEST,
                "decoded": PROFILE,
                "storage": PROFILE,
            },
            ("digest", "decoded_digest", "decoded", "storage"),
        ),
    },
    ("version", "plan_digest", "variant_id", "output_full_id", "execution", "artifact"),
)
RECORD_REF = obj(
    {
        "path": {**TEXT, "pattern": r"^records/[0-9a-f]{64}\.json(?![\s\S])"},
        "digest": DIGEST,
    },
    ("path", "digest"),
)
RECEIPT_LOCATION = {
    "oneOf": [
        obj(
            {"version": enum("2.0"), "digest": DIGEST, "receipt": ARTIFACT_RECEIPT},
            ("version", "digest", "receipt"),
        ),
        obj({"version": enum("2.0"), "record": RECORD_REF}, ("version", "record")),
    ]
}
MATERIALIZED = obj(
    {
        "version": enum("2.0"),
        "state": enum("materialized"),
        "required_features": FEATURES,
        "plan": OUTPUT_PLAN,
        "plan_digest": DIGEST,
        "mapping": obj(
            {
                "mode": enum("explicit"),
                "count": {"type": "integer", "minimum": 0},
                "index_digest": DIGEST,
                "receipts": enum("per_file"),
            },
            ("mode", "count", "index_digest", "receipts"),
        ),
    },
    ("version", "state", "plan", "plan_digest", "mapping"),
)
DEFINITIONS = {
    "execution_receipt": EXECUTION_RECEIPT,
    "artifact_receipt": ARTIFACT_RECEIPT,
    "output_plan": OUTPUT_PLAN,
    "receipt_location": RECEIPT_LOCATION,
    "materialized_transforms": MATERIALIZED,
    "output_encoding": ENCODING,
}
