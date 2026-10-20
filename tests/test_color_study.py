import numpy as np
import pytest

from canvastransfer import color_study as cs

COYOTE = (226, 156, 101)
ULTRAMARINE = (3, 25, 108)


def test_hex_code():
    assert cs.hex_code(COYOTE) == "#E29C65"


def test_lab_d50_matches_artistpigments_ultramarine():
    # the site lists 036 Ultramarine Blue as sRGB #03196c and L*a*b* 13.26 / 22.45 / -50.80 (D50)
    assert np.allclose(cs.lab_d50(ULTRAMARINE), [13.26, 22.45, -50.80], atol=0.5)


def test_munsell_notation_and_value():
    notation, value = cs.munsell(COYOTE)
    assert notation is not None and "YR" in notation
    assert 6.7 < value < 7.1  # Color Study shows "Value 7/10" for this swatch


def test_munsell_falls_back_to_value_for_colors_outside_the_data():
    notation, value = cs.munsell(ULTRAMARINE)
    assert notation is None
    assert abs(value - 1.42) < 0.1  # artistpigments.org lists value 1.42


def test_neutral_munsell():
    notation, value = cs.munsell((128, 128, 128))
    assert notation.startswith("N") and 5.0 < value < 5.5


@pytest.mark.parametrize("rgb,expected", [
    (COYOTE, "Very Warm"),
    ((0, 140, 200), "Very Cool"),  # cerulean
    ((40, 90, 200), "Cool"),  # violet-leaning blues read less cool, as painters describe ultramarine
    ((128, 128, 128), "Neutral"),
    ((140, 132, 128), "Neutral"),
])
def test_temperature(rgb, expected):
    assert cs.temperature(rgb)[1] == expected


def test_complement_of_orange_is_blue_and_keeps_lightness():
    comp = cs.complement(COYOTE)
    assert comp[2] > comp[0]  # blue-leaning
    assert abs(cs.lab_d65(comp)[0] - cs.lab_d65(COYOTE)[0]) < 1.5


def test_complement_of_saturated_color_stays_on_screen():
    comp = cs.complement((255, 0, 0))
    assert all(0 <= v <= 255 for v in comp)
    assert comp[1] > comp[0] or comp[2] > comp[0]  # cyan-ish, not red


def test_tints_shades_tones_run_from_color_toward_white_black_gray():
    t, s, g = cs.tints(COYOTE), cs.shades(COYOTE), cs.tones(COYOTE)
    for series in (t, s, g):
        assert len(series) == len(cs.MIX_STEPS) and series[0] == COYOTE
    assert min(t[-1]) > 230
    assert max(s[-1]) < 70
    assert max(g[-1]) - min(g[-1]) < max(COYOTE) - min(COYOTE)  # toward gray


def test_shade_of_yellow_goes_olive_like_paint():
    # RGB darkening keeps a dull yellow; pigment mixing with black shifts it toward green
    _, a_start, _ = cs.lab_d65((250, 220, 0))
    _, a_end, _ = cs.lab_d65(cs.shades((250, 220, 0))[3])
    assert a_end < a_start


def test_sample_average_over_area_ignores_transparent_pixels():
    img = np.zeros((10, 10, 4), dtype=np.uint8)
    img[:, :5] = (200, 0, 0, 255)
    img[:, 5:] = (0, 0, 200, 255)
    assert cs.sample_average(img, 2, 2, 0) == (200, 0, 0)
    assert cs.sample_average(img, 4.5, 5, 1) == (133, 0, 67)  # 2 red columns, 1 blue column
    img[:, 5:, 3] = 0
    assert cs.sample_average(img, 4.5, 5, 1) == (200, 0, 0)
    assert cs.sample_average(img, -1, 5, 1) is None


def test_similarity_mask_tolerance():
    img = np.zeros((4, 4, 4), dtype=np.uint8)
    img[...] = (200, 120, 80, 255)
    img[0, 0] = (205, 125, 85, 255)  # close
    img[3, 3] = (40, 80, 200, 255)  # far
    lab = cs.lab_image(img)
    tight = cs.similarity_mask(lab, [(200, 120, 80)], 1.0)
    loose = cs.similarity_mask(lab, [(200, 120, 80)], 10.0)
    assert tight.sum() == 14 and loose.sum() == 15 and not loose[3, 3]


def test_similarity_mask_unions_several_colors():
    img = np.zeros((1, 2, 4), dtype=np.uint8)
    img[0, 0] = (200, 0, 0, 255)
    img[0, 1] = (0, 0, 200, 255)
    mask = cs.similarity_mask(cs.lab_image(img), [(200, 0, 0), (0, 0, 200)], 2.0)
    assert mask.all()


def test_highlight_overlay_grays_rest_and_marks_matches():
    img = np.zeros((1, 2, 4), dtype=np.uint8)
    img[0, 0] = (200, 50, 50, 255)
    img[0, 1] = (10, 200, 10, 128)
    out = cs.highlight_overlay(img, np.array([[True, False]]))
    assert tuple(out[0, 0, :3]) == cs.HIGHLIGHT_RGB
    r, g, b, a = out[0, 1]
    assert r == g == b and a == 128
