"""Color Study through the real window: picking with mouse clicks, markers,
highlighting (checked on rendered pixels), removal, undo and saving."""

import numpy as np
import pytest

from canvastransfer import color_study as cs
from canvastransfer.models import Layer, Project, Swatch, new_id
from canvastransfer.project_io import ProjectDocument, load_project, save_project

COYOTE = (226, 156, 101)
BLUE = (40, 70, 180)


@pytest.fixture
def window(qapp):
    """A window with one layer: left half coyote, right half blue, filling a square canvas."""
    from canvastransfer.ui.main_window import MainWindow

    project = Project(name="T", canvas_width=10, canvas_height=10)
    layer = Layer(id=new_id("l"), name="photo", image_filename="p.png")
    img = np.zeros((200, 200, 4), dtype=np.uint8)
    img[:, :100] = (*COYOTE, 255)
    img[:, 100:] = (*BLUE, 255)
    doc = ProjectDocument(project)
    doc.set_layer_image(layer.id, img)
    project.add_layer(layer)
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    w._set_document(doc)
    qapp.processEvents()
    yield w, layer
    w.close()
    w.deleteLater()


def click(w, qapp, scene_x, scene_y):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    pos = w.canvas_view.mapFromScene(QPointF(scene_x, scene_y))
    QTest.mouseClick(w.canvas_view.viewport(), Qt.LeftButton, Qt.NoModifier, pos)
    qapp.processEvents()


def canvas_w(w):
    return w._canvas_size[0]


def test_pick_color_adds_swatch_where_clicked(window, qapp):
    w, layer = window
    w.pick_action.setChecked(True)
    assert w.side_tabs.currentIndex() == 1  # Color Study tab comes forward
    cw = canvas_w(w)
    click(w, qapp, cw * 0.25, cw * 0.5)
    click(w, qapp, cw * 0.75, cw * 0.5)
    swatches = w.doc.project.swatches
    assert [s.rgb for s in swatches] == [COYOTE, BLUE]
    assert abs(swatches[0].u - 0.25) < 0.02 and abs(swatches[0].v - 0.5) < 0.02
    assert swatches[0].layer_id == layer.id
    assert w.color_panel.swatch_list.count() == 2
    assert w.color_panel.hex_label.text() == cs.hex_code(BLUE)  # newest is selected


def test_click_outside_layer_adds_nothing(window, qapp):
    w, _ = window
    w._fit_active()
    w.doc.project.layers[0].quad = [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)]
    w._refresh_canvas()
    w.pick_action.setChecked(True)
    click(w, qapp, canvas_w(w) * 0.05, canvas_w(w) * 0.05)
    assert w.doc.project.swatches == []


def test_pick_and_transform_are_exclusive(window):
    w, _ = window
    w.pick_action.setChecked(True)
    w.transform_action.setChecked(True)
    assert not w.pick_action.isChecked()
    w.pick_action.setChecked(True)
    assert not w.transform_action.isChecked() and not w.history.in_session


def test_details_for_selected_swatch(window, qapp):
    w, _ = window
    w.pick_action.setChecked(True)
    click(w, qapp, canvas_w(w) * 0.25, canvas_w(w) * 0.5)
    panel = w.color_panel
    assert panel.hex_label.text() == "#E29C65"
    assert "Value 7/10" in panel.value_label.text()
    assert "Very Warm" in panel.temperature_label.text()
    assert "YR" in panel.munsell_label.text()
    assert len(panel.tints.colors()) == len(cs.MIX_STEPS)
    assert panel.complement.colors()[1][2] > panel.complement.colors()[1][0]  # blue complement


def test_clicking_marker_selects_swatch_instead_of_adding(window, qapp):
    w, _ = window
    w.pick_action.setChecked(True)
    cw = canvas_w(w)
    click(w, qapp, cw * 0.25, cw * 0.5)
    first = w.doc.project.swatches[0].id
    click(w, qapp, cw * 0.75, cw * 0.5)
    click(w, qapp, cw * 0.25, cw * 0.5)  # on marker 1
    assert len(w.doc.project.swatches) == 2
    assert w._selected_swatch_id == first


def test_markers_follow_the_layer(window, qapp):
    w, layer = window
    w.pick_action.setChecked(True)
    cw = canvas_w(w)
    click(w, qapp, cw * 0.25, cw * 0.5)
    marker = w.canvas_view._markers[0]
    before = w.canvas_view._marker_point(marker)
    w._flip(horizontal=True)
    after = w.canvas_view._marker_point(w.canvas_view._markers[0])
    assert abs(before.x() - cw * 0.25) < 3 and abs(after.x() - cw * 0.75) < 3


def test_highlight_marks_similar_pixels_yellow(window, qapp):
    w, _ = window
    w.pick_action.setChecked(True)
    cw = canvas_w(w)
    click(w, qapp, cw * 0.25, cw * 0.5)
    item = w.color_panel.swatch_list.item(0)
    from PySide6.QtCore import Qt

    item.setCheckState(Qt.Checked)
    assert w.doc.project.swatches[0].highlight
    img = w.canvas_view.render_canvas_image()
    left = img.pixelColor(round(cw * 0.25), round(cw * 0.5))
    right = img.pixelColor(round(cw * 0.75), round(cw * 0.5))
    assert (left.red(), left.green(), left.blue()) == cs.HIGHLIGHT_RGB
    assert right.red() == right.green() == right.blue()  # non-matching area shown in gray
    w.color_panel.swatch_list.item(0).setCheckState(Qt.Unchecked)  # list is rebuilt after each change
    img = w.canvas_view.render_canvas_image()
    c = img.pixelColor(round(cw * 0.25), round(cw * 0.5))
    assert (c.red(), c.green(), c.blue()) == COYOTE


def test_tolerance_widens_the_match(window, qapp):
    w, layer = window
    near = (210, 150, 105)  # about 8 units from coyote
    w.doc.project.swatches.append(Swatch(new_id("s"), layer.id, 0.25, 0.5, near, highlight=True))
    w._refresh_color_study()
    w.color_panel.tolerance.set(5)
    cw = canvas_w(w)

    def left_is_yellow():
        c = w.canvas_view.render_canvas_image().pixelColor(round(cw * 0.25), round(cw * 0.5))
        return (c.red(), c.green(), c.blue()) == cs.HIGHLIGHT_RGB

    assert not left_is_yellow()
    w.color_panel.tolerance.set(15)
    assert w.doc.project.highlight_tolerance == 15
    assert left_is_yellow()


def test_remove_and_undo(window, qapp):
    w, _ = window
    w.pick_action.setChecked(True)
    cw = canvas_w(w)
    click(w, qapp, cw * 0.25, cw * 0.5)
    click(w, qapp, cw * 0.75, cw * 0.5)
    w.color_panel.remove_button.click()
    assert [s.rgb for s in w.doc.project.swatches] == [COYOTE]
    assert w.color_panel.swatch_list.count() == 1
    w.undo_action.trigger()
    assert [s.rgb for s in w.doc.project.swatches] == [COYOTE, BLUE]
    w.undo_action.trigger()
    w.undo_action.trigger()
    assert w.doc.project.swatches == []
    assert w.canvas_view._markers == []


def test_deleting_layer_removes_its_swatches_and_undo_restores(window, qapp):
    w, layer = window
    w.pick_action.setChecked(True)
    click(w, qapp, canvas_w(w) * 0.25, canvas_w(w) * 0.5)
    w._on_delete_layer(layer.id)
    assert w.doc.project.swatches == []
    w.undo_action.trigger()
    assert len(w.doc.project.swatches) == 1


def test_swatches_save_and_load(window, qapp, tmp_path):
    w, layer = window
    w.pick_action.setChecked(True)
    click(w, qapp, canvas_w(w) * 0.25, canvas_w(w) * 0.5)
    w.doc.project.swatches[0].highlight = True
    w.doc.project.highlight_tolerance = 21.0
    save_project(w.doc, tmp_path / "p.ctproj")
    loaded = load_project(tmp_path / "p.ctproj").project
    assert loaded.swatches[0].rgb == COYOTE and loaded.swatches[0].highlight
    assert loaded.highlight_tolerance == 21.0
