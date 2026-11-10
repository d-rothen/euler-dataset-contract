from __future__ import annotations

import pytest

from euler_dataset_contract import (
    SOURCE_GRID_RULES,
    check_source_grid,
    resolve_source_grid,
    source_grid_from_rule,
    source_grid_matrix,
)


def _apply(grid, x, y):
    (sx, _, tx), (_, sy, ty) = grid["affine"]
    return sx * x + tx, sy * y + ty


def test_rules_cover_the_declared_set():
    assert SOURCE_GRID_RULES == ("identity", "resize", "crop_top_left", "crop_center")


def test_top_left_crop_is_the_identity_on_a_smaller_grid():
    grid = source_grid_from_rule("crop_top_left", (400, 879), (400, 872), source="rgb")
    assert grid == {"source": "rgb", "size": [400, 879], "affine": [[1, 0, 0], [0, 1, 0]]}


def test_centre_crop_floors_an_odd_offset():
    grid = source_grid_from_rule("crop_center", (10, 11), (8, 8))
    assert grid["affine"] == [[1, 0, -1], [0, 1, -1]]
    assert _apply(grid, 1, 1) == (0, 0)


def test_resize_maps_pixel_centres_and_edges():
    grid = source_grid_from_rule("resize", (400, 800), (200, 400))
    # Source pixels 0 and 1 straddle target pixel 0; the image edges coincide.
    assert _apply(grid, 0.5, 0.5) == (0.0, 0.0)
    assert _apply(grid, -0.5, -0.5) == (-0.5, -0.5)
    assert _apply(grid, 799.5, 399.5) == (399.5, 199.5)


def test_matrix_moves_intrinsics_like_a_resize():
    grid = source_grid_from_rule("resize", (400, 800), (200, 400))
    T = source_grid_matrix(grid)
    K = [[1000.0, 0.0, 399.5], [0.0, 1000.0, 199.5], [0.0, 0.0, 1.0]]
    K_out = [[sum(T[i][k] * K[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    # A principal point at the image centre stays at the resized centre.
    assert K_out[0][0] == 500.0 and K_out[0][2] == 199.5 and K_out[1][2] == 99.5


@pytest.mark.parametrize(
    "rule,source_size,size",
    [("identity", (4, 4), (4, 3)), ("crop_top_left", (4, 4), (5, 4)), ("tile", (4, 4), (4, 4))],
)
def test_rules_reject_sizes_they_cannot_describe(rule, source_size, size):
    with pytest.raises(ValueError):
        source_grid_from_rule(rule, source_size, size)


@pytest.mark.parametrize(
    "value,fragment",
    [
        ([], "an object"),
        ({"size": [4, 4]}, "'size' and 'affine'"),
        ({"size": [4, 4], "affine": [[1, 0, 0], [0, 1, 0]], "extra": 1}, "only"),
        ({"size": [4, 0], "affine": [[1, 0, 0], [0, 1, 0]]}, "'size'"),
        ({"size": [4, 4], "affine": [[1, 0, 0]]}, "2 rows of 3"),
        ({"size": [4, 4], "affine": [[1, 0, float("nan")], [0, 1, 0]]}, "2 rows of 3"),
        ({"size": [4, 4], "affine": [[1, 0.5, 0], [0, 1, 0]]}, "no rotation or shear"),
        ({"size": [4, 4], "affine": [[-1, 0, 0], [0, 1, 0]]}, "positive"),
        ({"source": "", "size": [4, 4], "affine": [[1, 0, 0], [0, 1, 0]]}, "'source'"),
    ],
)
def test_check_rejects_malformed_grids(value, fragment):
    assert fragment in check_source_grid(value)


def test_a_files_grid_overrides_the_heads():
    head = {"source_grid": {"size": [4, 4], "affine": [[1, 0, 0], [0, 1, 0]]}}
    file_grid = {"size": [4, 4], "affine": [[1, 0, -1], [0, 1, 0]]}
    assert resolve_source_grid(head, {"source_grid": file_grid}) == file_grid
    assert resolve_source_grid(head, {}) == head["source_grid"]
    assert resolve_source_grid({}, None) is None
    with pytest.raises(ValueError, match="attributes.source_grid"):
        resolve_source_grid(head, {"source_grid": {"size": [4, 4]}})
