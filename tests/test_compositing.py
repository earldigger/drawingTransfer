import numpy as np
import pytest

from canvastransfer.models import Transform, PerspectiveCorners, GridSettings, BlendMode
from canvastransfer.compositing import (
    to_float_rgba,
    to_uint8_rgba,
    perspective_correct,
    apply_transform,
    blend_over,
    blank_canvas,
    composite_layers,
    render_grid,
    split_view,
)


def solid_rgba(color, size):
    w, h = size
    img = np.empty((h, w, 4), dtype=np.float32)
    img[..., 0], img[..., 1], img[..., 2], img[..., 3] = color
    return img


def test_to_float_and_uint8_round_trip():
    uint8_img = np.full((4, 4, 3), 128, dtype=np.uint8)
    float_img = to_float_rgba(uint8_img)
    assert float_img.shape == (4, 4, 4)
    assert np.isclose(float_img[0, 0, 0], 128 / 255)
    assert float_img[0, 0, 3] == 1.0  # alpha added as fully opaque

    back = to_uint8_rgba(float_img)
    assert back[0, 0, 0] == 128


def test_perspective_correct_straightens_known_quad():
    # A 100x100 image whose "canvas" region is already axis-aligned; warping
    # it onto itself with the identity corners should be a no-op.
    img = solid_rgba((1.0, 0.0, 0.0, 1.0), (100, 100))
    corners = PerspectiveCorners(
        top_left=(0, 0), top_right=(99, 0), bottom_right=(99, 99), bottom_left=(0, 99)
    )
    out = perspective_correct(img, corners, (100, 100))
    assert out.shape == (100, 100, 4)
    assert np.allclose(out[50, 50], [1.0, 0.0, 0.0, 1.0], atol=0.05)


def test_perspective_correct_extracts_sub_rectangle():
    # Red square in the top-left quadrant of a larger green image; selecting
    # exactly that quadrant as the 4 corners should give back pure red.
    img = solid_rgba((0.0, 1.0, 0.0, 1.0), (200, 200))
    img[0:100, 0:100] = (1.0, 0.0, 0.0, 1.0)
    corners = PerspectiveCorners(
        top_left=(0, 0), top_right=(99, 0), bottom_right=(99, 99), bottom_left=(0, 99)
    )
    out = perspective_correct(img, corners, (50, 50))
    assert np.allclose(out[25, 25], [1.0, 0.0, 0.0, 1.0], atol=0.05)


def test_apply_transform_identity_centers_image_on_canvas():
    img = solid_rgba((1.0, 1.0, 1.0, 1.0), (10, 10))
    out = apply_transform(img, Transform(), canvas_size=(20, 20))
    assert out.shape == (20, 20, 4)
    assert np.allclose(out[10, 10], [1, 1, 1, 1], atol=0.05)
    assert out[1, 1, 3] < 0.1  # corners of the 20x20 canvas stay transparent


def test_apply_transform_offset_moves_image():
    img = solid_rgba((1.0, 1.0, 1.0, 1.0), (4, 4))
    out = apply_transform(img, Transform(offset_x=20, offset_y=0), canvas_size=(40, 10))
    # center would be at x=20 (canvas center) + 20 offset = 40 -> clipped near edge
    assert out[5, 38, 3] > 0.5
    assert out[5, 2, 3] < 0.1


def test_blend_normal_opacity_interpolates():
    base = solid_rgba((0.0, 0.0, 0.0, 1.0), (2, 2))
    top = solid_rgba((1.0, 1.0, 1.0, 1.0), (2, 2))
    out = blend_over(base, top, opacity=0.5, mode=BlendMode.NORMAL)
    assert np.allclose(out[0, 0, :3], [0.5, 0.5, 0.5], atol=0.01)
    assert np.isclose(out[0, 0, 3], 1.0)


def test_blend_multiply_darkens():
    base = solid_rgba((0.8, 0.8, 0.8, 1.0), (2, 2))
    top = solid_rgba((0.5, 0.5, 0.5, 1.0), (2, 2))
    out = blend_over(base, top, opacity=1.0, mode=BlendMode.MULTIPLY)
    assert np.allclose(out[0, 0, :3], [0.4, 0.4, 0.4], atol=0.01)


def test_blend_multiply_zero_opacity_is_noop():
    base = solid_rgba((0.8, 0.3, 0.1, 1.0), (2, 2))
    top = solid_rgba((0.0, 0.0, 0.0, 1.0), (2, 2))
    out = blend_over(base, top, opacity=0.0, mode=BlendMode.MULTIPLY)
    assert np.allclose(out[0, 0], base[0, 0], atol=0.01)


def test_composite_layers_stacks_bottom_to_top():
    size = (4, 4)
    bottom = solid_rgba((1.0, 0.0, 0.0, 1.0), size)
    top = solid_rgba((0.0, 0.0, 1.0, 0.5), size)
    out = composite_layers([(bottom, 1.0, BlendMode.NORMAL), (top, 1.0, BlendMode.NORMAL)], size)
    # 50% blue over opaque red -> 50/50 mix
    assert np.allclose(out[0, 0, :3], [0.5, 0.0, 0.5], atol=0.01)


def test_composite_layers_empty_is_white_canvas():
    out = composite_layers([], (3, 3))
    assert np.allclose(out, blank_canvas((3, 3)))


def test_render_grid_disabled_returns_transparent():
    grid = GridSettings(enabled=False)
    out = render_grid((40, 40), grid)
    assert np.all(out[..., 3] == 0)


def test_render_grid_draws_expected_number_of_divisions():
    grid = GridSettings(enabled=True, rows=1, columns=3, opacity=1.0, thickness_px=1)
    out = render_grid((30, 10), grid)
    # 2 vertical division lines for 3 columns, 0 horizontal for 1 row
    row_has_line = out[5, :, 3] > 0.5
    assert row_has_line.sum() >= 2  # at least the two divider columns are opaque


def test_render_grid_opacity_scales_alpha():
    grid = GridSettings(enabled=True, rows=2, columns=2, opacity=0.4, thickness_px=2)
    out = render_grid((20, 20), grid)
    max_alpha = out[..., 3].max()
    assert 0.3 < max_alpha <= 0.41


def test_split_view_picks_correct_side():
    size = (10, 10)
    left_img = solid_rgba((1.0, 0.0, 0.0, 1.0), size)
    right_img = solid_rgba((0.0, 0.0, 1.0, 1.0), size)
    out = split_view(left_img, right_img, split_position=0.5, divider_px=0)
    assert np.allclose(out[5, 1, :3], [1.0, 0.0, 0.0], atol=0.05)
    assert np.allclose(out[5, 8, :3], [0.0, 0.0, 1.0], atol=0.05)


@pytest.mark.parametrize("split_position", [0.0, 1.0])
def test_split_view_extremes_show_single_image(split_position):
    size = (10, 10)
    left_img = solid_rgba((1.0, 0.0, 0.0, 1.0), size)
    right_img = solid_rgba((0.0, 0.0, 1.0, 1.0), size)
    out = split_view(left_img, right_img, split_position=split_position, divider_px=0)
    expected = right_img if split_position == 0.0 else left_img
    assert np.allclose(out[5, 5, :3], expected[5, 5, :3], atol=0.05)
