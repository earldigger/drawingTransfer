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


def test_temperature_runs_blue_to_yellow():
    r, g, b = adjusted((150, 150, 150), temperature=1.0)
    assert r > 150 and g > 150 and b < 150 and r == g  # yellow
    r, g, b = adjusted((150, 150, 150), temperature=-1.0)
    assert r < 150 and g < 150 and b > 150  # blue


def test_tint_runs_green_to_magenta():
    r, g, b = adjusted((150, 150, 150), tint=1.0)
    assert g < 150 and r > 150 and b > 150 and r == b  # magenta
    r, g, b = adjusted((150, 150, 150), tint=-1.0)
    assert g > 150 and r < 150 and b < 150  # green


def test_temperature_and_tint_combine():
    alone = adjusted((150, 150, 150), temperature=0.5)
    both = adjusted((150, 150, 150), temperature=0.5, tint=0.5)
    assert both[1] < alone[1]  # tint pulls green down on top of the warm shift


def test_saturation_minus_one_is_gray():
    r, g, b = adjusted((200, 100, 50), saturation=-1.0)
    assert r == g == b


def test_saturation_boost_pushes_away_from_gray():
    r, g, b = adjusted((160, 120, 110), saturation=1.0)
    assert r > 160 and b < 110


def test_vibrance_affects_muted_colors_more_than_strong_ones():
    def spread(rgb):
        return max(rgb) - min(rgb)
    muted, strong = (140, 120, 115), (230, 40, 30)
    muted_gain = spread(adjusted(muted, vibrance=1.0)) / spread(muted)
    strong_gain = spread(adjusted(strong, vibrance=1.0)) / spread(strong)
    assert muted_gain > 1.4 and strong_gain < 1.25


def test_gray_stays_gray_under_vibrance_and_saturation():
    assert adjusted((90, 90, 90), vibrance=1.0, saturation=1.0) == (90, 90, 90)


def test_adjustments_keep_alpha():
    img = solid((100, 120, 140, 77), 3, 3)
    out = apply_adjustments(img, Adjustments(black=10, temperature=0.5, tint=-0.4, vibrance=0.5, saturation=-0.3))
    assert np.all(out[..., 3] == 77)
