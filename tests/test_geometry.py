import math

import pytest

from canvastransfer.geometry import (
    TransformMode,
    apply_drag,
    canvas_pixel_size,
    canvas_quad,
    centroid,
    denormalize_quad,
    fit_quad,
    flip_horizontal,
    flip_vertical,
    is_convex,
    normalize_quad,
    point_in_quad,
    rotation_handle,
)

SQUARE = [(100.0, 100.0), (300.0, 100.0), (300.0, 300.0), (100.0, 300.0)]


def close(a, b, tol=1e-6):
    return all(math.isclose(p[0], q[0], abs_tol=tol) and math.isclose(p[1], q[1], abs_tol=tol) for p, q in zip(a, b))


def width_height(q):
    return math.dist(q[0], q[1]), math.dist(q[0], q[3])


def test_canvas_pixel_size_keeps_aspect():
    w, h = canvas_pixel_size(16, 20)
    assert h == 1100 and abs(w / h - 0.8) < 0.01


def test_fit_quad_contains_wide_image_without_cropping():
    q = fit_quad(4000, 1000, 800, 1000)
    xs, ys = [p[0] for p in q], [p[1] for p in q]
    assert min(xs) >= 0 and max(xs) <= 800 and min(ys) >= 0 and max(ys) <= 1000
    w, h = width_height(q)
    assert math.isclose(w / h, 4.0)
    assert close([centroid(q)], [(400, 500)])


def test_normalize_round_trip():
    q = fit_quad(300, 200, 800, 1000)
    assert close(denormalize_quad(normalize_quad(q, 800, 1000), 800, 1000), q)


def test_move_translates_every_corner():
    q = apply_drag(TransformMode.UNIFORM, ("move",), SQUARE, (150, 150), (170, 140))
    assert close(q, [(x + 20, y - 10) for x, y in SQUARE])


def test_rotate_quarter_turn_about_center():
    c = centroid(SQUARE)
    start = (c[0] + 100, c[1])
    end = (c[0], c[1] + 100)  # 90 degrees clockwise on screen (y points down)
    q = apply_drag(TransformMode.UNIFORM, ("rotate",), SQUARE, start, end)
    assert close(q, [(300, 100), (300, 300), (100, 300), (100, 100)])


def test_uniform_corner_scale_keeps_aspect_and_anchor():
    q = apply_drag(TransformMode.UNIFORM, ("corner", 2), SQUARE, (300, 300), (500, 400))
    assert q[0] == SQUARE[0]  # opposite corner stays put
    w, h = width_height(q)
    assert math.isclose(w, h)
    assert w > 200


def test_free_edge_scale_changes_only_one_axis():
    q = apply_drag(TransformMode.FREE, ("edge", 1), SQUARE, (300, 200), (400, 250))
    w, h = width_height(q)
    assert math.isclose(w, 300) and math.isclose(h, 200)


def test_free_corner_scales_axes_independently():
    q = apply_drag(TransformMode.FREE, ("corner", 2), SQUARE, (300, 300), (500, 350))
    w, h = width_height(q)
    assert math.isclose(w, 400) and math.isclose(h, 250)


def test_free_scale_follows_rotated_layer_axes():
    rotated = apply_drag(TransformMode.UNIFORM, ("rotate",), SQUARE, (300, 200), (200, 300))
    mid_right = ((rotated[1][0] + rotated[2][0]) / 2, (rotated[1][1] + rotated[2][1]) / 2)
    c = centroid(rotated)
    outward = (mid_right[0] + (mid_right[0] - c[0]), mid_right[1] + (mid_right[1] - c[1]))
    q = apply_drag(TransformMode.FREE, ("edge", 1), rotated, mid_right, outward)
    w, h = width_height(q)
    assert math.isclose(w, 300, rel_tol=1e-6) and math.isclose(h, 200, rel_tol=1e-6)


def test_skew_edge_slides_along_edge_only():
    q = apply_drag(TransformMode.SKEW, ("edge", 0), SQUARE, (200, 100), (250, 60))
    assert close(q[:2], [(150, 100), (350, 100)])  # perpendicular part of the drag ignored
    assert close(q[2:], SQUARE[2:])


def test_distort_corner_moves_just_that_corner():
    q = apply_drag(TransformMode.DISTORT, ("corner", 1), SQUARE, (300, 100), (330, 80))
    assert q[1] == (330, 80)
    assert [q[0], q[2], q[3]] == [SQUARE[0], SQUARE[2], SQUARE[3]]


def test_distort_edge_moves_both_endpoints():
    q = apply_drag(TransformMode.DISTORT, ("edge", 2), SQUARE, (200, 300), (210, 340))
    assert close([q[2], q[3]], [(310, 340), (110, 340)])


def test_drag_that_folds_quad_is_rejected():
    assert apply_drag(TransformMode.DISTORT, ("corner", 0), SQUARE, (100, 100), (350, 350)) is None


def test_scale_cannot_collapse_or_invert():
    q = apply_drag(TransformMode.UNIFORM, ("corner", 2), SQUARE, (300, 300), (0, 0))
    assert q is None or is_convex(q)


def test_flip_horizontal_keeps_box_and_twice_is_identity():
    flipped = flip_horizontal(SQUARE)
    assert set(flipped) == set(SQUARE) and flipped != SQUARE
    assert flip_horizontal(flipped) == SQUARE
    assert is_convex(flipped)


def test_flip_vertical_twice_is_identity():
    assert flip_vertical(flip_vertical(SQUARE)) == SQUARE


def test_rotation_handle_sits_above_topmost_edge_even_when_flipped():
    for q in (SQUARE, flip_vertical(SQUARE)):
        handle, mid = rotation_handle(q, 40)
        assert mid == (200, 100)
        assert handle == (200, 60)


def test_point_in_quad():
    assert point_in_quad(SQUARE, (200, 200))
    assert not point_in_quad(SQUARE, (50, 200))
    assert point_in_quad(flip_horizontal(SQUARE), (200, 200))


@pytest.mark.parametrize("mode", list(TransformMode))
def test_every_mode_handles_every_handle(mode):
    handles = [("move",), ("rotate",)] + [("corner", i) for i in range(4)] + [("edge", i) for i in range(4)]
    for h in handles:
        q = apply_drag(mode, h, SQUARE, (200, 200), (205, 203))
        assert q is None or len(q) == 4


def test_canvas_quad():
    assert canvas_quad(10, 20) == [(0, 0), (10, 0), (10, 20), (0, 20)]
