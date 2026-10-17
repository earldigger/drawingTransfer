import numpy as np

from canvastransfer.models import PerspectiveCorners
from canvastransfer.image_ops import (
    adjust,
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


def test_adjust_noop_returns_input():
    img = solid((10, 20, 30, 255), 4, 4)
    assert adjust(img) is img


def test_invert_flips_rgb_and_keeps_alpha():
    img = solid((10, 200, 255, 128), 4, 4)
    out = adjust(img, invert=True)
    assert tuple(out[0, 0]) == (245, 55, 0, 128)
    assert tuple(img[0, 0]) == (10, 200, 255, 128)  # input untouched


def test_contrast_spreads_values_around_mid_gray():
    img = solid((100, 128, 160, 255), 2, 2)
    up = adjust(img, contrast=0.5)[0, 0]
    down = adjust(img, contrast=-0.5)[0, 0]
    assert up[0] < 100 and up[2] > 160
    assert 100 < down[0] < 128 < down[2] < 160
    assert up[3] == 255


def test_full_contrast_with_invert():
    out = adjust(solid((60, 60, 60, 255), 1, 1), contrast=1.0, invert=True)
    assert out[0, 0, 0] == 255 - max(0, round((60 - 127.5) * 4 + 127.5))
