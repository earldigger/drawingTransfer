"""Limited palettes: classic palettes filled from owned paints, your own
palettes (storage, editing, use on the Paints tab)."""

import numpy as np
import pytest

from canvastransfer import palettes
from canvastransfer.models import Layer, Project, new_id
from canvastransfer.paints import Paint, PaintLibrary, Palette
from canvastransfer.project_io import ProjectDocument


def p(pid, name, pigments, lab=(50.0, 10.0, 10.0), medium="oil", brand="B", **kw):
    return Paint(id=pid, medium=medium, brand=brand, name=name, pigments=pigments, lab=lab, **kw)


def studio():
    """A cut-down version of a real collection."""
    return PaintLibrary([
        p("lw", "Lead White", ["PW1"], (91.4, -1.2, 17.1)),
        p("lw2", "Lead White #2", ["PW1"], None, brand="Rublev"),
        p("tw", "Titanium White", ["PW6"], (97.1, -0.8, 2.3)),
        p("yo", "Yellow Ochre Deep", ["PY43"], (57.2, 26.9, 62.0)),
        p("vr", "Vermilion Red", ["PR255"], (48.3, 69.9, 53.0)),
        p("crs", "Cadmium Red Scarlet", ["PR108"], (52.9, 67.6, 75.3)),
        p("crp", "Cadmium Red Purple", ["PR108"], (27.7, 50.7, 29.2)),
        p("ib", "Ivory Black", ["PBk9"], (10.4, 0.0, -0.4)),
        p("er", "English Red", ["PR101"], (31.5, 33.2, 32.6)),
        p("cm", "Caput Mortuum Violet", ["PR101"], (22.3, 30.2, 19.8)),
        p("az", "Alizarin Crimson", ["PR83"], None),
        p("aze", "Alizarin Crimson Lake Extra", ["PV19", "PR177", "PBr23"], (29.2, 64.0, 43.5)),
        p("cb", "Cobalt Blue", ["PB28"], (20.9, 17.6, -55.6)),
        p("ub", "Ultramarine Blue", ["PB29"], (13.3, 22.5, -50.8)),
        p("sb", "Scheveningen Blue", ["PB15:3"], (8.5, 9.5, -30.6)),
        p("ce", "Cerulean Blue", ["PB35"], (33.7, -9.6, -41.8)),
        p("vi", "Viridian", ["PG18"], (51.1, -49.5, 3.9), medium="watercolor"),
    ])


def roles(filled):
    return {f.role.name: (f.paint.id if f.paint else None, f.substitute) for f in filled.roles}


def test_zorn_filled_from_owned_paints():
    lib = studio()
    got = roles(palettes.fill(palettes.template("zorn"), lib, "oil"))
    assert got == {"Lead white": ("lw", False), "Yellow ochre": ("yo", False),
                   "Vermilion": ("vr", False), "Ivory black": ("ib", False)}


def test_substitutes_when_the_historic_pigment_is_missing():
    lib = studio()
    for pid in ("lw", "lw2", "vr"):
        lib.remove(pid)
    got = roles(palettes.fill(palettes.template("zorn"), lib, "oil"))
    assert got["Lead white"] == ("tw", True)
    assert got["Vermilion"][1] and got["Vermilion"][0] in ("crs", "crp")


def test_roles_left_empty_and_paints_not_reused():
    lib = studio()
    filled = palettes.fill(palettes.template("sargent"), lib, "oil")
    got = roles(filled)
    assert got["Viridian"] == (None, False)  # only a watercolor viridian
    assert got["Red earth"] == ("er", False)  # by name, not Caput Mortuum
    assert got["Alizarin crimson / madder"] == ("az", False)  # genuine PR83 (via its stand-in color)
    ids = [p.id for p in filled.paints()]
    assert len(ids) == len(set(ids))


def test_split_primary_picks_warm_and_cool():
    got = roles(palettes.fill(palettes.template("split"), studio(), "oil"))
    assert got["Warm red"] == ("crs", False)  # "scarlet" preferred over Cadmium Red Purple
    assert got["Cool blue"] == ("sb", False)  # phthalo before the cerulean fallback
    assert got["Warm blue"] == ("ub", False)


def test_unticked_paints_are_not_used_by_classic_palettes():
    lib = studio()
    lib.get("ib").enabled = False
    assert roles(palettes.fill(palettes.template("zorn"), lib, "oil"))["Ivory black"][0] != "ib"


def test_every_template_role_is_well_formed():
    for t in palettes.TEMPLATES:
        assert t.roles and t.note
        for r in t.roles:
            assert r.pigments and all(code == code.upper() for code in r.pigments)


def test_palettes_saved_and_cleaned_up(tmp_path):
    lib = studio()
    lib.path = tmp_path / "paints.json"
    lib.palettes.append(Palette("pal-1", "Mine", "oil", ["ib", "er", "lw2"]))
    lib.changed()
    loaded = PaintLibrary.load(tmp_path / "paints.json")
    assert loaded.palettes[0].to_dict() == {"id": "pal-1", "name": "Mine", "medium": "oil",
                                            "paint_ids": ["ib", "er", "lw2"]}
    loaded.remove("er")
    assert loaded.palettes[0].paint_ids == ["ib", "lw2"]
    assert [x.id for x in loaded.palette_paints(loaded.palettes[0])] == ["ib", "lw2"]


def test_manual_stand_in_may_come_from_another_medium():
    lib = studio()
    oil_viridian = p("ov", "Viridian", ["PG18"], None)
    lib.paints.append(oil_viridian)
    assert lib.stand_in_for(oil_viridian) is None  # automatic stays within oil
    oil_viridian.stand_in = "vi"
    assert lib.color_of(oil_viridian) == lib.get("vi").lab


# -- through the window --------------------------------------------------------

@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("CANVASTRANSFER_DATA_DIR", str(tmp_path))
    from PySide6.QtWidgets import QMessageBox

    from canvastransfer.ui.main_window import MainWindow

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    project = Project(name="T", canvas_width=10, canvas_height=10)
    layer = Layer(id=new_id("l"), name="photo", image_filename="p.png")
    img = np.zeros((100, 100, 4), dtype=np.uint8)
    img[...] = (200, 150, 110, 255)
    doc = ProjectDocument(project)
    doc.set_layer_image(layer.id, img)
    project.add_layer(layer)
    w = MainWindow()
    w.resize(1300, 900)
    w.show()
    w._set_document(doc)
    for paint in studio().paints:
        w.paint_library.paints.append(paint)
    w.paint_library.changed()
    w.paint_panel.reload_library()
    w.doc.project.swatches.clear()
    from canvastransfer.models import Swatch

    swatch = Swatch(new_id("s"), layer.id, 0.5, 0.5, (200, 150, 110))
    w.doc.project.swatches.append(swatch)
    w._selected_swatch_id = swatch.id
    w._refresh_all()
    qapp.processEvents()
    yield w
    w.close()
    w.deleteLater()


def test_new_palette_dialog(window, qapp):
    from canvastransfer.ui.palette_dialog import PaletteDialog

    d = PaletteDialog(window.paint_library)
    assert not d.ok_button.isEnabled()
    d.name.setText("Portrait")
    for pid in ("ib", "er", "yo", "lw2", "az"):
        d.check(pid)
    d.filter.setText("white")
    visible = [d.list.item(i).text() for i in range(d.list.count()) if not d.list.item(i).isHidden()]
    assert all("White" in t for t in visible)
    assert d.ok_button.isEnabled() and "5 paints" in d.count.text()
    palette = d.result_palette()
    assert palette.name == "Portrait" and palette.medium == "oil"
    assert set(palette.paint_ids) == {"ib", "er", "yo", "lw2", "az"}


def test_palette_dialog_keeps_one_medium(window):
    from canvastransfer.ui.palette_dialog import PaletteDialog

    d = PaletteDialog(window.paint_library)
    d.name.setText("X")
    d.check("ib")
    d.medium.setCurrentIndex(d.medium.findData("watercolor"))
    d.check("vi")
    assert d.result_palette().paint_ids == ["vi"]


def test_duplicate_classic_and_delete(window):
    window.open_paint_library(palettes=True)
    dlg = window.library_dialog
    assert dlg.tabs.currentIndex() == 1
    dlg.select_source(("template", "zorn"))
    texts = [dlg.palette_contents.item(i).text() for i in range(dlg.palette_contents.count())]
    assert texts[0].startswith("Lead white:  Lead White")
    dlg.duplicate_palette()
    mine = window.paint_library.palettes[0]
    assert mine.name == "My Zorn" and mine.paint_ids == ["lw", "yo", "vr", "ib"]
    assert window.paint_panel.group.findData(f"palette:{mine.id}") >= 0
    dlg.select_source(("palette", mine.id))
    dlg.delete_palette()
    assert window.paint_library.palettes == []
    assert window.paint_panel.group.findData(f"palette:{mine.id}") < 0


def test_paints_tab_mixes_only_from_the_palette(window, qapp):
    lib = window.paint_library
    lib.palettes.append(Palette("pal-1", "Earthy", "oil", ["er", "yo", "lw2", "ib"]))
    lib.changed()
    window.paint_panel.reload_library()
    window.side_tabs.setCurrentIndex(2)
    panel = window.paint_panel
    panel.select_source("palette:pal-1")
    qapp.processEvents()
    assert panel.lightener.currentData() == "lw2"  # the palette's own white
    used = {paint.id for r in panel.result().singles + panel.result().pairs for paint, _ in r.parts}
    assert used <= {"er", "yo", "lw2", "ib"}
    assert not panel.favorites_only.isEnabled()
    assert "Earthy" in panel.group.currentText()


def test_paints_tab_classic_palette_and_missing_roles(window, qapp):
    window.side_tabs.setCurrentIndex(2)
    panel = window.paint_panel
    panel.select_source("template:sargent:oil")
    qapp.processEvents()
    assert "None of your paints fits: cadmium yellow, viridian" in panel.palette_label.text()
    assert panel.lightener.currentData() == "lw"
    used = {paint.id for r in panel.result().pairs for paint, _ in r.parts}
    assert used <= {p.id for p in palettes.fill(palettes.template("sargent"), window.paint_library, "oil").paints()}


def test_palette_reports_paints_without_color(window, qapp):
    lib = window.paint_library
    lib.paints.append(p("ny", "Naples Yellow Light Genuine", ["PY41"], None, brand="Vasari"))
    lib.palettes.append(Palette("pal-2", "Mine", "oil", ["ny", "ib"]))
    lib.changed()
    window.paint_panel.reload_library()
    window.side_tabs.setCurrentIndex(2)
    window.paint_panel.select_source("palette:pal-2")
    qapp.processEvents()
    assert "No color data (left out): Naples Yellow Light Genuine" in window.paint_panel.palette_label.text()
