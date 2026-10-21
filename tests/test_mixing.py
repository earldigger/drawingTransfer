"""Recipe search: the vectorized Mixbox matches the library, and the search
finds mixes that were made on purpose."""

import time

import mixbox
import numpy as np
import pytest

from canvastransfer import color_study as cs
from canvastransfer import mixing
from canvastransfer.paints import Paint, PaintLibrary

LABS = {  # CIELAB D50 masstones from artistpigments.org
    "Old Delft Blue": ((5.385, 9.614, -19.735), ["PB60"]),
    "Cadmium Red Medium": ((41.208, 67.65, 51.874), ["PR108"]),
    "Yellow Ochre Deep": ((57.224, 26.917, 62.045), ["PY43"]),
    "Burnt Umber": ((18.349, 3.607, 6.658), ["PBr7"]),
    "Viridian": ((51.084, -49.548, 3.862), ["PG18"]),
    "Titanium White": ((97.050, -0.773, 2.258), ["PW6"]),
}


def paint(name, lab=None, pigments=None):
    lab_, pig = LABS.get(name, (lab, pigments or []))
    return Paint(id=name.lower().replace(" ", "-"), medium="oil", brand="B", name=name,
                 pigments=pig, lab=lab if lab is not None else lab_)


@pytest.fixture
def library():
    return PaintLibrary([paint(n) for n in LABS])


def screen(p):
    return cs.lab_d50_to_srgb(p.lab)[0]


def test_vectorized_mixbox_matches_mixbox():
    rng = np.random.default_rng(3)
    for _ in range(20):
        c1, c2 = (tuple(int(v) for v in rng.integers(0, 256, 3)) for _ in range(2))
        t = float(rng.random())
        assert np.abs(np.array(mixing.mix([c1, c2], [1 - t, t])) - mixbox.lerp(c1, c2, t)).max() <= 1


def test_vectorized_lab_matches_colour_science():
    for rgb in [(239, 165, 106), (3, 25, 108), (0, 0, 0), (255, 255, 255)]:
        assert np.allclose(cs.srgb_to_lab_d50(np.array(rgb) / 255), cs.lab_d50(rgb), atol=1e-6)


def test_finds_a_single_paint_tint(library):
    red, white = library.get("cadmium-red-medium"), library.get("titanium-white")
    target = mixing.mix([screen(red), screen(white)], [0.3, 0.7])
    result = mixing.find_recipes(target, library, library.paints, white)
    best = result.singles[0]
    assert best.parts[0][0] is red and best.parts[0][1] == pytest.approx(0.3, abs=0.02)
    assert best.parts[-1][0] is white
    assert best.delta_e < 0.5


def test_finds_a_two_paint_mix(library):
    blue, ochre, white = (library.get(i) for i in ("old-delft-blue", "yellow-ochre-deep", "titanium-white"))
    target = mixing.mix([screen(blue), screen(ochre), screen(white)], [0.35, 0.3, 0.35])
    result = mixing.find_recipes(target, library, library.paints, white)
    assert result.pairs[0].delta_e < 1.0
    assert any({p.id for p, _ in r.parts} >= {blue.id, ochre.id} for r in result.pairs)
    for r in result.pairs:
        assert sum(s for _, s in r.parts) == pytest.approx(1.0, abs=0.01)
        assert r.parts[-1][0] is white  # white listed last


def test_without_lightener_paints_are_used_straight(library):
    result = mixing.find_recipes(screen(library.get("viridian")), library, library.paints, None)
    assert result.singles[0].parts == [(library.get("viridian"), 1.0)]
    assert result.singles[0].delta_e < 0.5
    assert all(len(r.parts) == 1 for r in result.singles)
    assert all(len(r.parts) == 2 for r in result.pairs)  # whites count as ordinary paints here


def test_stand_ins_share_a_slot_and_are_flagged(library):
    umber = library.get("burnt-umber")
    cassel = Paint(id="cassel", medium="oil", brand="C", name="Cassel Earth", pigments=["PBr7"])
    library.paints.append(cassel)
    result = mixing.find_recipes(screen(umber), library, library.paints, library.get("titanium-white"))
    best = result.singles[0]
    assert best.parts[0][0] is umber and best.also[umber.id] == [cassel]
    library.get("burnt-umber").enabled = False
    only_cassel = [p for p in library.paints if p.enabled]
    best = mixing.find_recipes(screen(umber), library, only_cassel, library.get("titanium-white")).singles[0]
    assert best.parts[0][0] is cassel and best.stand_ins == [cassel]


def test_off_screen_paints_are_flagged(library):
    red = library.get("cadmium-red-medium")
    assert not cs.lab_d50_to_srgb(red.lab)[1]
    result = mixing.find_recipes((230, 60, 40), library, library.paints, library.get("titanium-white"))
    assert red in result.singles[0].off_screen


def test_paints_without_color_are_skipped():
    lib = PaintLibrary([paint("Anise", None, ["PY74"])])
    assert mixing.find_recipes((100, 150, 60), lib, lib.paints, None) == mixing.MatchResult([], [])


def test_water_lightens_watercolor():
    lib = PaintLibrary([paint("Viridian")])
    target = mixing.mix([screen(lib.paints[0]), (255, 255, 255)], [0.4, 0.6])
    best = mixing.find_recipes(target, lib, lib.paints, mixing.WATER).singles[0]
    assert best.parts[-1][0] is mixing.WATER and best.delta_e < 0.5


def test_search_is_quick_for_fifty_paints():
    rng = np.random.default_rng(1)
    paints = [paint(f"P{i}", (float(rng.uniform(10, 90)), float(rng.uniform(-60, 60)), float(rng.uniform(-60, 60))),
                    ["PR1"]) for i in range(50)]
    lib = PaintLibrary(paints + [paint("Titanium White")])
    mixing.find_recipes((120, 140, 90), lib, lib.paints, lib.get("titanium-white"))  # warm up
    start = time.perf_counter()
    mixing.find_recipes((120, 140, 90), lib, lib.paints, lib.get("titanium-white"))
    assert time.perf_counter() - start < 1.0


def test_closeness_words():
    assert mixing.closeness(0.5) == "very close"
    assert mixing.closeness(3) == "close"
    assert mixing.closeness(12) == "far off"
