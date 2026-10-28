"""Kubelka-Munk mixing: spectra that reproduce each color, mixes that
behave like paint, and the recipe search running on it."""

import time

import numpy as np
import pytest

from canvastransfer import compare_mixing, km_mixing as km, mixing
from canvastransfer.paints import Paint, PaintLibrary

RED, WHITE, BLUE, YELLOW = (200, 40, 40), (245, 245, 245), (25, 40, 140), (250, 210, 0)


def test_each_color_comes_back_exactly():
    rng = np.random.default_rng(2)
    for _ in range(100):
        c = tuple(int(v) for v in rng.integers(0, 256, 3))
        assert km.mix([c], [1.0]) == c


def test_reflectance_is_in_range_and_as_smooth_as_colour_science():
    colour = pytest.importorskip("colour")
    shape = colour.SpectralShape(*km.WAVELENGTHS)
    cmfs = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"].copy().align(shape)
    d65 = colour.SDS_ILLUMINANTS["D65"].copy().align(shape)
    for c in [(250, 210, 0), (25, 40, 140), (0, 255, 0), (128, 128, 128)]:
        r = km.reflectance(c)
        assert r.shape == (km.BANDS,) and r.min() >= km.R_MIN and r.max() <= 1.0
        xyz = colour.sRGB_to_XYZ(np.array(c) / 255.0)
        meng = np.clip(colour.XYZ_to_sd(xyz, method="Meng 2015", cmfs=cmfs, illuminant=d65).values, km.R_MIN, 1)
        # the same problem; colour-science lets pure green go above 1, which paint can't
        assert np.abs(r - meng).max() < 0.1


def test_white_makes_a_tint_not_a_red():
    tint = km.mix([RED, WHITE], [0.5, 0.5])
    assert tint[1] > RED[1] + 30 and tint[2] > RED[2] + 30  # visibly lighter, unlike plain Kubelka-Munk
    assert km.mix([RED, WHITE], [0.5, 0.5]) == km.mix([WHITE, RED], [0.5, 0.5])


def test_blue_and_yellow_make_green_not_gray():
    r, g, b = km.mix([BLUE, YELLOW], [0.5, 0.5])
    assert g > r and g > b
    avg = [(x + y) / 2 for x, y in zip(BLUE, YELLOW)]
    assert avg[0] > avg[1]  # averaging the screen colors does not


def test_recipe_search_with_kubelka_munk_finds_its_own_mix():
    red = Paint(id="red", medium="oil", brand="B", name="Red", lab=(41.2, 67.6, 51.9))
    blue = Paint(id="blue", medium="oil", brand="B", name="Blue", lab=(20.0, 20.0, -50.0))
    white = Paint(id="white", medium="oil", brand="B", name="White", pigments=["PW6"], lab=(97.0, -0.8, 2.3))
    lib = PaintLibrary([red, blue, white])
    screen = {p.id: compare_mixing.screen_rgb(lib, p) for p in lib.paints}
    target = mixing.mix([screen["red"], screen["blue"], screen["white"]], [0.3, 0.2, 0.5], mixing.KUBELKA_MUNK)
    result = mixing.find_recipes(target, lib, lib.paints, white, mixing.KUBELKA_MUNK)
    best = result.pairs[0]
    assert best.delta_e < 1
    rgb, de = mixing.predict(best, target, mixing.KUBELKA_MUNK)
    assert rgb == best.rgb and de < 1
    _, other = mixing.predict(best, target, mixing.MIXBOX)
    assert other >= 0


def test_search_is_quick_for_fifty_paints():
    rng = np.random.default_rng(1)
    paints = [Paint(id=f"p{i}", medium="oil", brand="B", name=f"P{i}",
                    lab=(float(rng.uniform(10, 90)), float(rng.uniform(-60, 60)), float(rng.uniform(-60, 60))))
              for i in range(50)]
    white = Paint(id="w", medium="oil", brand="B", name="White", pigments=["PW6"], lab=(97.0, -0.8, 2.3))
    lib = PaintLibrary(paints + [white])
    start = time.perf_counter()
    mixing.find_recipes((120, 140, 90), lib, lib.paints, white, mixing.KUBELKA_MUNK)  # includes the spectra
    assert time.perf_counter() - start < 3.0


def test_comparison_page(tmp_path):
    out = tmp_path / "c.html"
    compare_mixing.main([str(out)])
    page = out.read_text()
    assert "Ultramarine Blue + Cadmium Yellow Medium" in page and "Kubelka-Munk's recipe" in page
