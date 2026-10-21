"""Paint library: reading saved artistpigments.org pages, stand-ins,
pasted color text, merging re-imports, and storage."""

from pathlib import Path

import pytest

from canvastransfer.paints import Paint, PaintLibrary, name_similarity, parse_collection_html, parse_lab_text

FIXTURE = Path(__file__).parent / "fixtures" / "collection_sample.html"


def sample():
    return parse_collection_html(FIXTURE.read_text(encoding="utf-8"))


def by_name(paints, name):
    return next(p for p in paints if p.name == name)


def oil(name, pigments, lab=None, **kw):
    return Paint(id=name.lower().replace(" ", "-"), medium=kw.pop("medium", "oil"), brand="B", name=name,
                 pigments=pigments, lab=lab, **kw)


def test_parse_saved_collection_page():
    title, paints = sample()
    assert title == "Test paints"
    assert len(paints) == 8
    delft = by_name(paints, "Old Delft Blue")
    assert delft.brand == "Old Holland Classic Oil Colours" and delft.code == "220"
    assert delft.pigments == ["PB60"] and delft.opacity == "O" and delft.medium == "oil"
    assert delft.lab == pytest.approx((5.385, 9.614, -19.735))
    assert delft.source == "Chart"
    assert delft.url == "https://artistpigments.org/brands/old-holland-classic-oil-colours/dyoq9-old-delft-blue"
    anise = by_name(paints, "Anise")
    assert anise.lab is None and anise.brand == "Charvin Fine & Extra Fine Oil Colors"
    assert anise.pigments == ["PY74", "PY65", "PG7"]
    assert anise.url.endswith("/m27hg-anise")
    assert by_name(paints, "Viridian").medium == "watercolor"


def test_page_without_paints_is_refused():
    with pytest.raises(ValueError):
        parse_collection_html("<html><body>Log in to see this page</body></html>")


def test_auto_stand_in_prefers_same_pigments_then_names():
    _, paints = sample()
    lib = PaintLibrary(paints)
    # same single pigment (PR108); the closest name wins over other PR108 paints
    lib.paints.append(oil("Cadmium Red Scarlet", ["PR108"], (52.9, 67.6, 75.3)))
    charvin_red = by_name(paints, "Medium Cadmium red (Genuine)")
    assert lib.stand_in_for(charvin_red).name == "Cadmium Red Medium"
    # nothing with PB29 yet
    charvin_blue = by_name(paints, "Light Ultramarine Blue")
    assert lib.stand_in_for(charvin_blue) is None
    lib.paints.append(oil("Ultramarine Blue", ["PB29"], (13.26, 22.45, -50.80)))
    assert lib.stand_in_for(charvin_blue).name == "Ultramarine Blue"
    assert lib.color_of(charvin_blue) == (13.26, 22.45, -50.80)
    assert lib.stand_in_for(by_name(paints, "Anise")) is None


def test_stand_in_stays_within_its_medium():
    lib = PaintLibrary([oil("Viridian", ["PG18"], (51, -49, 4), medium="watercolor"), oil("Viridian Hue", ["PG18"])])
    assert lib.stand_in_for(lib.paints[1]) is None


def test_name_match_needs_a_shared_pigment_when_names_differ():
    lib = PaintLibrary([oil("Caput Mortuum Violet (Mars)", ["PR101"], (22, 30, 20)),
                        oil("Caput Mortum", ["PR101", "PB29", "PV23"]),
                        oil("Cobalt Violet Dark", ["PV14"], (18, 37, -4)),
                        oil("Light Cobalt Violet (Hue)", ["PR122", "PV23"])])
    assert lib.stand_in_for(lib.paints[1]).name == "Caput Mortuum Violet (Mars)"  # misspelled, shares PR101
    assert lib.stand_in_for(lib.paints[3]) is None  # similar name, different pigments


def test_chosen_or_refused_stand_in():
    lib = PaintLibrary([oil("Burnt Umber", ["PBr7"], (18, 4, 7)), oil("Raw Umber", ["PBr7"], (30, 3, 12)),
                        oil("Cassel Earth", ["PBr7"])])
    cassel = lib.paints[2]
    cassel.stand_in = "raw-umber"
    assert lib.stand_in_for(cassel).name == "Raw Umber"
    cassel.stand_in = ""
    assert lib.stand_in_for(cassel) is None and lib.color_of(cassel) is None
    cassel.stand_in = "raw-umber"
    lib.remove("raw-umber")
    assert cassel.stand_in is None  # back to automatic
    assert lib.stand_in_for(cassel).name == "Burnt Umber"


def test_name_similarity():
    assert name_similarity("Medium Cadmium Red (Genuine)", "Cadmium Red Medium") == 1.0
    assert name_similarity("Titanium Zinc White", "Titanium White") == pytest.approx(0.8)
    assert name_similarity("Cassel Earth", "Burnt Umber") == 0.0


@pytest.mark.parametrize("text, expected", [
    ("L* 13.26 a* 22.45 b* -50.80", (13.26, 22.45, -50.80)),
    ("13.26, 22.45, -50.80", (13.26, 22.45, -50.80)),
    ("13,26  22,45  −50,80", (13.26, 22.45, -50.80)),
    ("CIELAB D50 2°: 36.221 61.334 46.048", (36.221, 61.334, 46.048)),
    ("", None),
    ("12 34", None),
    ("150 0 0", None),
])
def test_parse_lab_text(text, expected):
    result = parse_lab_text(text)
    assert result == (pytest.approx(expected) if expected else None)


def test_parse_hex_as_srgb():
    # artistpigments lists 036 Ultramarine Blue as #03196c and L*a*b* 13.26 / 22.45 / -50.80 (D50)
    assert parse_lab_text("#03196c") == pytest.approx((13.26, 22.45, -50.80), abs=0.3)


def test_reimport_updates_site_data_and_keeps_your_choices(tmp_path):
    _, paints = sample()
    lib = PaintLibrary(path=tmp_path / "paints.json")
    report = lib.merge(paints)
    assert (report.added, report.updated) == (8, 0)
    delft = lib.get("dyoq9")
    delft.favorite, delft.enabled = True, False
    by_name(lib.paints, "Anise").stand_in = "dyoq9"
    manual = Paint(id="manual-1", medium="oil", brand="Old Holland Classic Oil Colours", name="Ultramarine Blue",
                   code="036", pigments=["PB29"], lab=(13.26, 22.45, -50.8), source="Entered by hand")
    lib.add(manual)
    _, again = sample()
    by_name(again, "Old Delft Blue").lab = (6.0, 9.0, -20.0)  # the site re-measured it
    report = lib.merge(again)
    assert (report.added, report.updated, report.kept) == (0, 8, [])
    delft = lib.get("dyoq9")
    assert delft.lab == (6.0, 9.0, -20.0)
    assert delft.favorite and not delft.enabled
    assert by_name(lib.paints, "Anise").stand_in == "dyoq9"
    assert lib.get("manual-1") is not None and lib.get("manual-1").manual


def test_save_and_load(tmp_path):
    _, paints = sample()
    lib = PaintLibrary(path=tmp_path / "sub" / "paints.json")
    lib.merge(paints)
    lib.paints[0].favorite = True
    lib.changed()
    loaded = PaintLibrary.load(tmp_path / "sub" / "paints.json")
    assert [p.to_dict() for p in loaded.paints] == [p.to_dict() for p in lib.paints]
    assert loaded.media() == ["oil", "watercolor"]
    assert PaintLibrary.load(tmp_path / "missing.json").paints == []


def test_whites():
    assert oil("Titanium Zinc White", ["PW4", "PW5", "PW6"]).is_white
    assert not oil("Brilliant Yellow Reddish", ["PW4", "PW6", "PY53", "PO73"]).is_white
