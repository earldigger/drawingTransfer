"""Undo/redo and transform Done/Cancel, driven through the real window."""

import pytest

from canvastransfer.models import CompareMode

from tests.window_helpers import make_window_with_layers


@pytest.fixture
def window(qapp):
    w, layers = make_window_with_layers((20, 10), (20, 10))
    yield w, layers
    w.deleteLater()


def shifted(quad, dx):
    return [(x + dx, y) for x, y in quad]


def drag_to(w, layer, dx):
    """What the canvas reports at the end of a mouse drag that moved `layer` by dx px."""
    current = w.canvas_view.quad(layer.id)
    w.canvas_view.quadCommitted.emit(layer.id, shifted(current, dx))


def test_cancel_reverts_every_drag_in_the_session(window):
    w, (_, top) = window
    original = list(top.quad)
    w.transform_action.setChecked(True)
    drag_to(w, top, 50)
    drag_to(w, top, 30)
    assert top.quad != original

    w.cancel_action.trigger()

    restored = w.doc.project.get_layer(top.id)
    assert restored.quad == original
    assert not w.transform_action.isChecked()
    assert not w.history.can_undo()  # the cancelled session left no history


def test_done_makes_the_session_one_undo_step(window):
    w, (_, top) = window
    original = list(top.quad)
    w.transform_action.setChecked(True)
    drag_to(w, top, 50)
    drag_to(w, top, 30)
    moved = list(w.doc.project.get_layer(top.id).quad)

    w.done_action.trigger()
    assert not w.transform_action.isChecked()

    w.undo_action.trigger()
    assert w.doc.project.get_layer(top.id).quad == original
    assert not w.history.can_undo()

    w.redo_action.trigger()
    assert w.doc.project.get_layer(top.id).quad == moved


def test_turning_transform_off_counts_as_done(window):
    w, (_, top) = window
    w.transform_action.setChecked(True)
    drag_to(w, top, 50)
    w.transform_action.setChecked(False)
    assert not w.history.in_session
    assert w.history.can_undo()


def test_undo_inside_session_steps_back_one_drag(window):
    w, (_, top) = window
    original = list(top.quad)
    w.transform_action.setChecked(True)
    drag_to(w, top, 50)
    after_first = list(w.doc.project.get_layer(top.id).quad)
    drag_to(w, top, 30)

    w.undo_action.trigger()
    assert w.doc.project.get_layer(top.id).quad == after_first
    assert w.history.in_session and w.transform_action.isChecked()

    w.undo_action.trigger()
    assert w.doc.project.get_layer(top.id).quad == original
    assert not w.undo_action.isEnabled()


def test_slider_drag_is_a_single_undo_step(window):
    w, (_, top) = window
    for value in (90, 80, 70, 60, 50):
        w.layers_panel.opacity_slider.setValue(value)
    assert w.doc.project.get_layer(top.id).opacity == 0.5
    w.undo_action.trigger()
    assert w.doc.project.get_layer(top.id).opacity == 1.0
    assert not w.history.can_undo()


def test_undo_delete_brings_layer_and_image_back(window):
    w, (bottom, top) = window
    w._on_delete_layer(top.id)
    assert w.doc.project.get_layer(top.id) is None and top.id not in w.doc.images

    w.undo_action.trigger()
    assert w.doc.project.get_layer(top.id) is not None
    assert top.id in w.doc.images
    assert w.canvas_view.entry(top.id) is not None

    w.redo_action.trigger()
    assert w.doc.project.get_layer(top.id) is None


def test_other_edit_during_session_commits_it_first(window):
    w, (_, top) = window
    original = list(top.quad)
    w.transform_action.setChecked(True)
    drag_to(w, top, 50)

    w.layers_panel.invert_check.setChecked(True)

    assert not w.history.in_session and not w.transform_action.isChecked()
    w.undo_action.trigger()  # undoes invert
    layer = w.doc.project.get_layer(top.id)
    assert not layer.adjustments.invert and layer.quad != original
    w.undo_action.trigger()  # undoes the transform
    assert w.doc.project.get_layer(top.id).quad == original


def test_switching_layer_keeps_transforming_and_commits_previous(window):
    w, (bottom, top) = window
    top_original = list(top.quad)
    w.transform_action.setChecked(True)
    drag_to(w, top, 50)

    w.layers_panel.list_widget.setCurrentRow(1)  # bottom layer
    assert w.doc.project.active_layer_id == bottom.id
    assert w.history.in_session and w.transform_action.isChecked()

    w.cancel_action.trigger()  # cancels only the (empty) bottom-layer session
    assert w.doc.project.get_layer(top.id).quad != top_original
    w.undo_action.trigger()
    assert w.doc.project.get_layer(top.id).quad == top_original


def test_undo_keeps_compare_settings(window):
    w, (bottom, top) = window
    w.layers_panel.invert_check.setChecked(True)
    w.doc.project.compare_mode = CompareMode.BLINK_A
    w.undo_action.trigger()
    assert w.doc.project.compare_mode == CompareMode.BLINK_A


def test_new_document_clears_history(window):
    w, layers = window
    w.layers_panel.invert_check.setChecked(True)
    other, _ = make_window_with_layers((5, 5))
    w._set_document(other.doc)
    assert not w.undo_action.isEnabled()
    other.deleteLater()


def test_undo_buttons_disabled_with_nothing_to_undo(window):
    w, _ = window
    assert not w.undo_action.isEnabled() and not w.redo_action.isEnabled()
    assert not w.done_action.isEnabled() and not w.cancel_action.isEnabled()


def test_levels_slider_drag_is_one_undo_step(window):
    w, (_, top) = window
    for value in (10, 20, 30, 40):
        w.layers_panel.black.slider.setValue(value)
    assert w.doc.project.get_layer(top.id).adjustments.black == 40
    w.undo_action.trigger()
    assert w.doc.project.get_layer(top.id).adjustments.black == 0
    assert w.layers_panel.black.slider.value() == 0  # panel follows the undo


def test_reset_color_is_undoable(window):
    w, (_, top) = window
    w.layers_panel.saturation.slider.setValue(-50)
    w.layers_panel.hue_sat_reset.click()
    assert w.doc.project.get_layer(top.id).adjustments.saturation == 0
    w.undo_action.trigger()
    assert w.doc.project.get_layer(top.id).adjustments.saturation == -50
