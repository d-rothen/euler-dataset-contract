"""``source_grid``: how a dataset's pixel grid derives from another grid.

A modality whose samples were computed from other images -- a model's
prediction from its input, a crop or resize of a source dataset -- records the
relation as the shared ``modality.meta.source_grid`` when it holds for every
sample, or as a file's ``attributes.source_grid`` when it varies per sample.
The file's value wins::

    {"source": "rgb", "size": [400, 879], "affine": [[1, 0, 0], [0, 1, 0]]}

``size``
    ``[height, width]`` of the source grid.
``affine``
    Maps a source pixel position to this grid, with pixel centres at integer
    coordinates: ``x' = affine[0][0] * x + affine[0][2]`` and
    ``y' = affine[1][1] * y + affine[1][2]``. It is the pixel-grid transform
    ``T`` that moves a camera as ``K_out = T @ K_in`` (with ``[0, 0, 1]`` as
    the third row). Only crops and resizes are expressible: positive scales
    and zero off-diagonal terms. A top-left crop is the identity, a crop at
    ``(top, left)`` the offset ``(-left, -top)``, and resizing ``W`` columns
    to ``w`` the scale ``s = w / W`` with offset ``0.5 * s - 0.5``.
``source``
    Optional name of what the grid derives from, such as the input modality.

The module is pure Python, so producers and consumers share one convention
without importing an array library.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Optional

#: Rules a producer may declare instead of a matrix; see
#: :func:`source_grid_from_rule`.
SOURCE_GRID_RULES = ("identity", "resize", "crop_top_left", "crop_center")

_KEYS = {"source", "size", "affine"}


def _is_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _is_positive_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def check_source_grid(value: Any) -> Optional[str]:
    """Return why *value* is not a valid ``source_grid``, or ``None``.

    The message completes "must be ..." so it reads like the contract's other
    meta-field errors.
    """
    if not isinstance(value, Mapping):
        return "an object with 'size' and 'affine'"
    unknown = sorted(set(value) - _KEYS)
    if unknown:
        return f"an object with only 'source', 'size' and 'affine' (got {unknown})"
    if "size" not in value or "affine" not in value:
        return "an object with 'size' and 'affine'"
    source = value.get("source")
    if source is not None and (not isinstance(source, str) or not source.strip()):
        return "an object whose 'source' is a non-empty string"
    size = value["size"]
    if not (
        isinstance(size, list) and len(size) == 2 and all(map(_is_positive_int, size))
    ):
        return "an object whose 'size' is [height, width] of positive integers"
    affine = value["affine"]
    if not (
        isinstance(affine, list)
        and len(affine) == 2
        and all(isinstance(row, list) and len(row) == 3 for row in affine)
        and all(_is_number(item) for row in affine for item in row)
    ):
        return "an object whose 'affine' is 2 rows of 3 finite numbers"
    if affine[0][1] != 0 or affine[1][0] != 0:
        return (
            "an object whose 'affine' is [[sx, 0, tx], [0, sy, ty]]: "
            "only crops and resizes, no rotation or shear"
        )
    if affine[0][0] <= 0 or affine[1][1] <= 0:
        return "an object whose 'affine' scales sx and sy are positive"
    return None


def validate_source_grid(value: Any, context: str = "source_grid") -> dict[str, Any]:
    """Return a copy of *value* after checking it; raise ``ValueError`` if invalid."""
    error = check_source_grid(value)
    if error is not None:
        raise ValueError(f"{context} must be {error}")
    result: dict[str, Any] = {
        "size": list(value["size"]),
        "affine": [list(row) for row in value["affine"]],
    }
    if value.get("source") is not None:
        result = {"source": value["source"], **result}
    return result


def _size(value: Any, name: str) -> tuple[int, int]:
    if not (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(map(_is_positive_int, value))
    ):
        raise ValueError(f"{name} must be (height, width) of positive integers, got {value!r}")
    return int(value[0]), int(value[1])


def source_grid_from_rule(
    rule: str,
    source_size: Any,
    size: Any,
    *,
    source: Optional[str] = None,
) -> dict[str, Any]:
    """Return the ``source_grid`` a declared *rule* gives for these sizes.

    *source_size* is the ``(height, width)`` of the image the sample was
    computed from, *size* the sample's own. The rules:

    - ``"identity"``: the same grid; the sizes must match;
    - ``"resize"``: the whole source stretched to *size* (pixel centres,
      ``align_corners=False``);
    - ``"crop_top_left"``: the top-left *size* pixels of the source, e.g. a
      latent model that floors each side to a multiple of 8;
    - ``"crop_center"``: the centred *size* pixels, the top-left offset
      floored for an odd difference.

    A relation the sizes do not determine, such as a resize to an
    intermediate size followed by a crop, needs its matrix written directly.
    """
    source_h, source_w = _size(source_size, "source_size")
    height, width = _size(size, "size")
    if rule == "identity":
        if (height, width) != (source_h, source_w):
            raise ValueError(
                f"source_grid rule 'identity' needs equal sizes, got source "
                f"{source_h}x{source_w} and sample {height}x{width}"
            )
        affine = [[1, 0, 0], [0, 1, 0]]
    elif rule == "resize":
        sx, sy = width / source_w, height / source_h
        affine = [[sx, 0, 0.5 * sx - 0.5], [0, sy, 0.5 * sy - 0.5]]
    elif rule in {"crop_top_left", "crop_center"}:
        if height > source_h or width > source_w:
            raise ValueError(
                f"source_grid rule {rule!r} needs a sample no larger than its "
                f"source, got source {source_h}x{source_w} and sample {height}x{width}"
            )
        top = (source_h - height) // 2 if rule == "crop_center" else 0
        left = (source_w - width) // 2 if rule == "crop_center" else 0
        affine = [[1, 0, -left], [0, 1, -top]]
    else:
        raise ValueError(
            f"Unknown source_grid rule {rule!r}; expected one of {list(SOURCE_GRID_RULES)}"
        )
    grid: dict[str, Any] = {"size": [source_h, source_w], "affine": affine}
    if source is not None:
        grid = {"source": source, **grid}
    return validate_source_grid(grid)


def resolve_source_grid(
    head_meta: Optional[Mapping[str, Any]],
    attributes: Optional[Mapping[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Return a sample's ``source_grid``: its file's, else its head's, else ``None``."""
    for origin, container in (("attributes", attributes), ("modality.meta", head_meta)):
        if isinstance(container, Mapping) and container.get("source_grid") is not None:
            return validate_source_grid(container["source_grid"], f"{origin}.source_grid")
    return None


def source_grid_matrix(grid: Mapping[str, Any]) -> list[list[float]]:
    """Return *grid*'s affine as a ``3x3`` matrix ``T`` with ``K_out = T @ K_in``."""
    affine = validate_source_grid(grid)["affine"]
    return [list(map(float, affine[0])), list(map(float, affine[1])), [0.0, 0.0, 1.0]]


SOURCE_GRID_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["size", "affine"],
    "additionalProperties": False,
    "properties": {
        "source": {"type": "string", "minLength": 1},
        "size": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
            "minItems": 2,
            "maxItems": 2,
        },
        "affine": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": False,
            "prefixItems": [
                {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": False,
                    "prefixItems": [
                        {"type": "number", "exclusiveMinimum": 0},
                        {"const": 0},
                        {"type": "number"},
                    ],
                },
                {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": False,
                    "prefixItems": [
                        {"const": 0},
                        {"type": "number", "exclusiveMinimum": 0},
                        {"type": "number"},
                    ],
                },
            ],
        },
    },
    "examples": [
        {"source": "rgb", "size": [400, 879], "affine": [[1, 0, 0], [0, 1, 0]]},
        {"size": [480, 960], "affine": [[0.8, 0, -0.1], [0, 0.8, -0.1]]},
    ],
}
