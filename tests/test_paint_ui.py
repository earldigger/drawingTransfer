"""Paint Library window, Edit Paint dialog and the Paints tab, driven
through the real window."""

from pathlib import Path

import numpy as np
import pytest

from canvastransfer.models import Layer, Project, new_id
from canvastransfer.paints import PaintLibrary
from canvastransfer.ui.paint_library import COL_DATA, COL_NAME, EDITED_MARK
from canvastransfer.project_io import ProjectDocument

FIXTURE = Path(__file__).parent / "fixtures" / "collection_sample.html"
MUTED_BLUE = (70, 94, 139)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CANVASTRANSFER_DATA_DIR", str(tmp_path))
    from PySide6.QtWidgets import QMessageBox

    messages = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: messages.append(a[2])))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: messages.append(a[2])))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    return tmp_path, messages


@pytest.fixture
def window(qapp, data_dir):
    from canvastransfer.ui.main_window import MainWindow

    project = Project(name="T", canvas_width=10, canvas_height=10)
    layer = Layer(id=new_id("l"), name="photo", image_filename="p.png")
    img = np.zeros((100, 100, 4), dtype=np.uint8)
    img[...] = (*MUTED_BLUE, 255)
    doc = ProjectDocument(project)
    doc.set_layer_image(layer.id, img)
    project.add_layer(layer)
    w = MainWindow()
    w.resize(1300, 900)
    w.show()
    w._set_document(doc)
    qapp.processEvents()
    yield w
    w.close()
    w.deleteLater()


def imported(w):
    w.open_paint_library()
    w.library_dialog.import_page(str(FIXTURE))
    return w.library_dialog


def tree_rows(dialog):
    rows = {}
    for g in range(dialog.tree.topLevelItemCount()):
        group = dialog.tree.topLevelItem(g)
        for c in range(group.childCount()):
            item = group.child(c)
            rows[item.text(COL_NAME).replace(EDITED_MARK, '')] = (group.text(COL_NAME), item)
    return rows


def add_swatch(w, qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    w.pick_action.setChecked(True)
    cw = w._canvas_size[0]
    QTest.mouseClick(w.canvas_view.viewport(), Qt.LeftButton, Qt.NoModifier,
                     w.canvas_view.mapFromScene(QPointF(cw * 0.5, cw * 0.5)))
    qapp.processEvents()


def test_import_groups_paints_by_medium_and_saves(window, data_dir):
    tmp, messages = data_dir
    dialog = imported(window)
    rows = tree_rows(dialog)
    assert rows["Old Delft Blue"][0].startswith("Oil")
    assert rows["Viridian"][0].startswith("Watercolor")
    assert "Stand-in: Cadmium Red Medium" in rows["Medium Cadmium red (Genuine)"][1].text(COL_DATA)
    assert rows["Anise"][1].text(COL_DATA) == "No color data"
    assert rows["Cadmium Red Medium"][1].text(COL_DATA).startswith("⚠")  # outside what a screen can show
    assert "8 paints added" in messages[-1]
    assert len(PaintLibrary.load(tmp / "paints.json").paints) == 8


def test_favorite_and_use_checkboxes(window, qapp):
    from PySide6.QtCore import Qt

    dialog = imported(window)
    item = tree_rows(dialog)["Old Delft Blue"][1]
    item.setCheckState(0, Qt.Checked)
    assert window.paint_library.get("dyoq9").favorite
    qapp.processEvents()  # the tree is rebuilt just after the click
    item = tree_rows(dialog)["Old Delft Blue"][1]
    item.setCheckState(1, Qt.Unchecked)
    assert not window.paint_library.get("dyoq9").enabled
    assert not PaintLibrary.load(window.paint_library.path).get("dyoq9").enabled


def test_add_paint_by_pasting_lab(window, qapp):
    from canvastransfer.ui.paint_dialog import PaintDialog

    imported(window)
    lib = window.paint_library
    d = PaintDialog(lib)
    d.brand.setText("Old Holland Classic Oil Colours")
    d.name.setText("Ultramarine Blue")
    d.lightfastness.setCurrentText("I")
    d.drying.setText("medium")
    d.pigments.setText("pb29")
    d.color_text.setText("CIELAB D50 2°: L* 13.26  a* 22.45  b* -50.80")
    assert "#03196C" in d.color_note.text()
    assert not d.stand_in.isEnabled()
    paint = d.result_paint()
    assert paint.lab == (13.26, 22.45, -50.80) and paint.pigments == ["PB29"] and paint.manual
    assert (paint.lightfastness, paint.drying) == ("I", "medium")
    lib.add(paint)
    # the Charvin PB29 now borrows its color automatically
    assert lib.stand_in_for(lib.get("68xmv")).name == "Ultramarine Blue"


def test_bad_color_text_blocks_ok(window):
    from canvastransfer.ui.paint_dialog import PaintDialog

    d = PaintDialog(PaintLibrary())
    d.name.setText("X")
    d.color_text.setText("about blue")
    assert not d.ok_button.isEnabled()
    d.color_text.setText("")
    assert d.ok_button.isEnabled()


def test_choose_a_stand_in(window):
    from canvastransfer.ui.paint_dialog import PaintDialog

    imported(window)
    lib = window.paint_library
    anise = lib.get("m27hg")
    d = PaintDialog(lib, anise)
    assert d.stand_in.isEnabled() and d.stand_in.currentData() is None  # automatic
    d.stand_in.setCurrentIndex(d.stand_in.findData("dyoq9"))
    d.result_paint()
    assert anise.stand_in == "dyoq9" and lib.color_of(anise) == lib.get("dyoq9").lab


def test_delete_paint(window):
    dialog = imported(window)
    dialog.tree.setCurrentItem(tree_rows(dialog)["Anise"][1])
    dialog.delete_selected()
    assert window.paint_library.get("m27hg") is None
    assert "Anise" not in tree_rows(dialog)


def test_paints_tab_matches_selected_swatch(window, qapp):
    imported(window)
    add_swatch(window, qapp)
    window.side_tabs.setCurrentIndex(2)
    qapp.processEvents()
    panel = window.paint_panel
    assert panel.group.currentData() == "medium:oil"
    assert "Titanium White" in panel.lightener.currentText()
    result = panel.result()
    assert result.singles and result.pairs
    assert result.pairs[0].delta_e < 3
    assert panel.singles.count() == len(result.singles)
    assert "ΔE" in panel.singles.item(0).text()


def test_watercolor_group_lightens_with_water(window, qapp):
    imported(window)
    add_swatch(window, qapp)
    window.side_tabs.setCurrentIndex(2)
    panel = window.paint_panel
    panel.select_source("medium:watercolor")
    qapp.processEvents()
    assert panel.lightener.currentData() == "water"
    assert all(p.medium == "watercolor" or p.id == "water" for r in panel.result().singles for p, _ in r.parts)
    panel.select_source("medium:oil")
    assert "Titanium White" in panel.lightener.currentText()


def test_paints_tab_stays_forward_when_selecting_swatches(window, qapp):
    imported(window)
    add_swatch(window, qapp)
    add_swatch(window, qapp)  # clicking the marker selects swatch 1
    window.side_tabs.setCurrentIndex(2)
    window._select_swatch(window.doc.project.swatches[0].id)
    assert window.side_tabs.currentIndex() == 2


def test_paints_tab_without_swatch_or_paints(window, qapp):
    window.side_tabs.setCurrentIndex(2)
    qapp.processEvents()
    assert "Select a swatch" in window.paint_panel.target_label.text()
    add_swatch(window, qapp)
    qapp.processEvents()
    assert "library is empty" in window.paint_panel.target_label.text()


def test_damaged_library_is_set_aside(qapp, data_dir):
    from canvastransfer.ui.main_window import MainWindow

    tmp, messages = data_dir
    (tmp / "paints.json").write_text("{not json", encoding="utf-8")
    w = MainWindow()
    assert w.paint_library.paints == []
    assert (tmp / "paints.damaged.json").exists()
    assert "set aside" in messages[-1]
    w.deleteLater()


def test_mixing_model_choice_and_cross_check(window, qapp):
    imported(window)
    add_swatch(window, qapp)
    window.side_tabs.setCurrentIndex(2)
    qapp.processEvents()
    panel = window.paint_panel
    assert panel.model.currentText() == "Mixbox"
    assert "Kubelka-Munk: ΔE" in panel.pairs.item(0).text()
    panel.model.setCurrentIndex(panel.model.findData("km"))
    qapp.processEvents()
    assert panel.mix_model().name == "Kubelka-Munk"
    assert panel.result().pairs  # no closeness check: tints of near-black paints are where the models differ
    assert "Mixbox: ΔE" in panel.pairs.item(0).text()


def test_edit_paint_sets_strength(window):
    from canvastransfer.paints import Paint, PaintLibrary
    from canvastransfer.ui.paint_dialog import PaintDialog

    blue = Paint(id="b", medium="oil", brand="B", name="Delft", lab=(5.4, 9.6, -19.7))
    dialog = PaintDialog(PaintLibrary([blue]), blue)
    assert dialog.strength.value() == 1.0
    dialog.strength.setValue(3.0)
    assert dialog.result_paint().strength == 3.0
