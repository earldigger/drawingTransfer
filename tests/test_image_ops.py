import numpy as np

from canvastransfer.models import Adjustments, PerspectiveCorners
from canvastransfer.image_ops import (
    apply_adjustments,
    levels_curve,
    capped_size,
    corrected_size,
    downscale_to_max,
    perspective_correct,
)


def solid(color, w, h):
    img = np.empty((h, w, 4), dtype=np.uint8)
    img[...] = color
    return img


def test_perspective_correct_extracts_marked_region():
    img = solid((0, 255, 0, 255), 200, 200)
    img[0:100, 0:100] = (255, 0, 0, 255)
    corners = PerspectiveCorners((0, 0), (100, 0), (100, 100), (0, 100))
    out = perspective_correct(img, corners, (50, 50))
    assert out.shape == (50, 50, 4)
    assert tuple(out[25, 25]) == (255, 0, 0, 255)


def test_corrected_size_uses_longest_opposite_edges():
    corners = PerspectiveCorners((0, 0), (400, 20), (380, 300), (10, 290))
    w, h = corrected_size(corners)
    assert 395 < w < 405 and 285 < h < 300


def test_capped_size_only_shrinks():
    assert capped_size(1000, 500, 2400) == (1000, 500)
    assert capped_size(4800, 2400, 2400) == (2400, 1200)


def test_downscale_to_max_returns_same_array_when_small():
    img = solid((1, 2, 3, 255), 10, 10)
    assert downscale_to_max(img, 100) is img
    assert downscale_to_max(solid((1, 2, 3, 255), 400, 200), 100).shape == (50, 100, 4)


def close(a, b, tol=3):
    return all(abs(int(x) - int(y)) <= tol for x, y in zip(a, b))


def adjusted(rgb, **kw):
    return tuple(apply_adjustments(solid((*rgb, 255), 1, 1), Adjustments(**kw))[0, 0, :3])


def test_no_adjustment_returns_input_unchanged():
    img = solid((10, 20, 30, 255), 4, 4)
    assert apply_adjustments(img, Adjustments()) is img


def test_invert_flips_rgb_keeps_alpha_and_input():
    img = solid((10, 200, 255, 128), 4, 4)
    out = apply_adjustments(img, Adjustments(invert=True))
    assert tuple(out[0, 0]) == (245, 55, 0, 128)
    assert tuple(img[0, 0]) == (10, 200, 255, 128)


def test_levels_dark_and_light_points_stretch_range():
    assert adjusted((50, 50, 50), black=50) == (0, 0, 0)
    assert adjusted((200, 200, 200), white=200) == (255, 255, 255)
    # halfway between the two points lands on mid-gray
    assert adjusted((125, 125, 125), black=50, white=200)[0] in (127, 128)


def test_levels_midtones_lighten_and_darken_but_keep_ends():
    assert adjusted((128, 128, 128), gamma=2.0)[0] > 170
    assert adjusted((128, 128, 128), gamma=0.5)[0] < 80
    assert adjusted((0, 0, 0), gamma=2.0) == (0, 0, 0)
    assert adjusted((255, 255, 255), gamma=0.5) == (255, 255, 255)


def test_levels_curve_is_monotonic():
    curve = levels_curve(30, 1.7, 220)
    assert np.all(np.diff(curve) >= 0)
    assert curve[30] == 0 and curve[220] == 1


def test_invert_happens_before_levels():
    # inverted 230 -> 25, which is under the dark point -> black
    assert adjusted((230, 230, 230), invert=True, black=40) == (0, 0, 0)


def test_hue_shift_rotates_around_the_wheel():
    assert close(adjusted((255, 0, 0), hue=120), (0, 255, 0))
    assert close(adjusted((255, 0, 0), hue=-120), (0, 0, 255))
    assert close(adjusted((255, 0, 0), hue=180), (0, 255, 255))


def test_hue_shift_wraps_reds_just_below_360_degrees():
    # (255, 0, 1) is 359.8 degrees, which OpenCV stores as hue 180
    assert close(adjusted((255, 0, 1), hue=120), (0, 255, 0))


def test_hue_shift_leaves_grays_alone():
    assert close(adjusted((90, 90, 90), hue=77), (90, 90, 90))


def test_saturation_minus_100_is_gray():
    r, g, b = adjusted((200, 100, 50), saturation=-100)
    assert abs(r - g) <= 1 and abs(g - b) <= 1


def test_saturation_boost_pushes_away_from_gray():
    r, g, b = adjusted((160, 120, 110), saturation=60)
    assert r > 160 and b < 110


def test_lightness_blends_toward_white_or_black():
    assert adjusted((100, 50, 200), lightness=100) == (255, 255, 255)
    assert adjusted((100, 50, 200), lightness=-100) == (0, 0, 0)
    assert close(adjusted((100, 100, 100), lightness=50), (178, 178, 178))
    assert close(adjusted((100, 100, 100), lightness=-50), (50, 50, 50))


def test_colorize_tints_everything_one_hue_keeping_lightness():
    dark = adjusted((40, 40, 40), colorize=True, colorize_hue=240, colorize_saturation=60)
    light = adjusted((200, 200, 200), colorize=True, colorize_hue=240, colorize_saturation=60)
    for r, g, b in (dark, light):
        assert b > r and abs(r - g) <= 2  # blue tint
    assert sum(map(int, light)) > sum(map(int, dark))  # light stays lighter than dark
    # a red pixel gets the same blue tint: its own color is discarded
    red = adjusted((200, 30, 30), colorize=True, colorize_hue=240, colorize_saturation=60)
    assert red[2] > red[0]


def test_colorize_with_zero_saturation_is_grayscale():
    r, g, b = adjusted((200, 30, 30), colorize=True, colorize_saturation=0)
    assert abs(r - g) <= 1 and abs(g - b) <= 1


def test_colorize_ignores_regular_hue_and_saturation():
    a = adjusted((120, 80, 60), colorize=True, colorize_hue=30, hue=90, saturation=-50)
    b = adjusted((120, 80, 60), colorize=True, colorize_hue=30)
    assert a == b


def test_adjustments_keep_alpha():
    img = solid((100, 120, 140, 77), 3, 3)
    for adj in (Adjustments(black=10, hue=40, saturation=-30, lightness=20), Adjustments(colorize=True, lightness=-10)):
        assert np.all(apply_adjustments(img, adj)[..., 3] == 77)
