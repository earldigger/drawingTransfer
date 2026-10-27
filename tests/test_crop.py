"""Cropping a reference: the crop math, saving it, drawing it, and the Crop
tool in the window (one undo step, Cancel, references only)."""

import pytest

from canvastransfer.compare import DisplayState
from canvastransfer.geometry import FULL_CROP, MIN_CROP, drag_crop, flip_horizontal
from canvastransfer.models import BlendMode, Layer, LayerKind, new_id

from tests.test_canvas_view import FULL, SIZE, render, rgb, solid_pixmap, view  # noqa: F401  (fixture)
from tests.window_helpers import make_window_with_layers

WHITE = (255, 255, 255)
RED = (255, 0, 0)


# -- crop math ---------------------------------------------------------------------


def test_dragging_a_corner_moves_its_two_sides():
    assert drag_crop(FULL_CROP, ("crop-corner", 0), (0, 0), (0.1, 0.2)) == (0.1, 0.2, 1.0, 1.0)
    assert drag_crop(FULL_CROP, ("crop-corner", 2), (1, 1), (0.7, 0.6)) == (0.0, 0.0, 0.7, 0.6)


def test_dragging_an_edge_moves_only_that_side():
    assert drag_crop(FULL_CROP, ("crop-edge", 1), (1, 0.5), (0.8, 0.9)) == (0.0, 0.0, 0.8, 1.0)


def test_crop_stays_inside_the_image_and_never_collapses():
    assert drag_crop(FULL_CROP, ("crop-corner", 0), (0, 0), (-0.5, -0.5)) == FULL_CROP
    left, _, right, _ = drag_crop((0.1, 0.1, 0.5, 0.5), ("crop-edge", 1), (0.5, 0.3), (0.0, 0.3))
    assert right - left == pytest.approx(MIN_CROP)


def test_sliding_the_crop_keeps_its_size_and_stays_inside():
    assert drag_crop((0.1, 0.1, 0.5, 0.5), ("crop-move",), (0.3, 0.3), (0.9, 0.0)) == pytest.approx((0.6, 0.0, 1.0, 0.4))


# -- saving ----------------------------------------------------------------------------


def test_crop_round_trips_and_older_projects_have_none():
    layer = Layer(id=new_id("l"), name="r", image_filename="r.png", crop=(0.1, 0.2, 0.8, 0.9))
    assert Layer.from_dict(layer.to_dict()).crop == (0.1, 0.2, 0.8, 0.9)
    old = layer.to_dict()
    old.pop("crop")
    assert Layer.from_dict(old).crop is None


# -- drawing -----------------------------------------------------------------------------


def cropped_entry(crop, quad=FULL):
    from canvastransfer.ui.canvas_view import LayerEntry

    return LayerEntry("a", solid_pixmap(RED), quad, DisplayState(True, 1.0, BlendMode.NORMAL), crop)


def test_only_the_cropped_part_is_drawn(view):
    view.show_layers([cropped_entry((0.0, 0.0, 0.5, 1.0))], None)  # keep the left half
    img = render(view)
    assert rgb(img, 25, 50) == RED
    assert rgb(img, 75, 50) == WHITE


def test_crop_moves_with_the_layer(view):
    """The crop belongs to the image: flipping the layer puts the kept half on the other side."""
    view.show_layers([cropped_entry((0.0, 0.0, 0.5, 1.0), quad=flip_horizontal(FULL))], None)
    img = render(view)
    assert rgb(img, 25, 50) == WHITE
    assert rgb(img, 75, 50) == RED


def test_cropped_multiply_layer_is_clipped_too(view):
    from canvastransfer.ui.canvas_view import LayerEntry

    below = LayerEntry("below", solid_pixmap((200, 200, 200)), FULL, DisplayState(True, 1.0, BlendMode.NORMAL))
    top = LayerEntry("top", solid_pixmap((0, 0, 0)), FULL, DisplayState(True, 1.0, BlendMode.MULTIPLY), (0.0, 0.0, 1.0, 0.5))
    view.show_layers([below, top], None)
    img = render(view)
    assert rgb(img, 50, 25) == (0, 0, 0)
    assert rgb(img, 50, 75) == (200, 200, 200)


# -- the Crop tool ----------------------------------------------------------------------------


@pytest.fixture
def window(qapp):
    w, layers = make_window_with_layers((20, 10), (20, 10))
    yield w, layers
    w.deleteLater()


def crop_drag(w, layer, crop):
    """What the canvas reports at the end of a crop drag."""
    w.canvas_view.cropCommitted.emit(layer.id, crop)


def test_crop_turns_on_transform_and_done_is_one_undo_step(window):
    w, (_, top) = window
    w.crop_action.setChecked(True)
    assert w.transform_action.isChecked() and w.history.in_session
    crop_drag(w, top, (0.1, 0.0, 1.0, 1.0))
    crop_drag(w, top, (0.1, 0.0, 0.7, 1.0))
    w.done_action.trigger()
    assert top.crop == (0.1, 0.0, 0.7, 1.0)
    assert not w.crop_action.isChecked() and not w.transform_action.isChecked()
    w._undo()
    assert w._active_layer().crop is None


def test_cancel_reverts_the_crop(window):
    w, (_, top) = window
    w.crop_action.setChecked(True)
    crop_drag(w, top, (0.2, 0.2, 0.8, 0.8))
    w.cancel_action.trigger()
    assert w._active_layer().crop is None


def test_reset_crop_shows_the_whole_reference(window):
    w, (_, top) = window
    w.crop_action.setChecked(True)
    crop_drag(w, top, (0.2, 0.2, 0.8, 0.8))
    w.done_action.trigger()
    assert w.reset_crop_action.isEnabled()
    w.reset_crop_action.trigger()
    assert w._active_layer().crop is None


def test_canvas_photos_cannot_be_cropped(window):
    w, (bottom, _) = window
    bottom.kind = LayerKind.CANVAS
    w._on_layer_selected(bottom.id)
    assert not w.crop_action.isEnabled()


def test_picking_ignores_the_cropped_off_part(window):
    w, (_, top) = window
    top.crop = (0.0, 0.0, 0.5, 1.0)
    w._refresh_canvas()
    quad = w.canvas_view.quad(top.id)
    (x0, y0), (x1, _), _, (_, y3) = quad
    y = (y0 + y3) / 2
    assert w._sample_at(x0 + (x1 - x0) * 0.25, y) is not None
    assert w._sample_at(x0 + (x1 - x0) * 0.75, y) is None


def test_dragging_a_crop_corner_with_the_mouse(view, qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    from canvastransfer.geometry import TransformMode

    committed = []
    view.cropCommitted.connect(lambda lid, crop: committed.append((lid, crop)))
    view.show_layers([cropped_entry(None, quad=[(20, 20), (60, 20), (60, 60), (20, 60)])], None)
    view.set_active_layer("a")
    view.set_tool(True, TransformMode.UNIFORM)
    view.set_crop_mode(True)
    assert view._hit(view.mapFromScene(QPointF(60, 60))) == ("crop-corner", 2)
    assert view._hit(view.mapFromScene(QPointF(40, 40))) == ("crop-move",)

    start = view.mapFromScene(QPointF(60, 60))
    end = view.mapFromScene(QPointF(50, 40))  # bottom-right corner in to (0.75, 0.5) of the image
    QTest.mousePress(view.viewport(), Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseRelease(view.viewport(), Qt.LeftButton, Qt.NoModifier, end)
    (lid, crop), = committed
    assert lid == "a" and crop == pytest.approx((0.0, 0.0, 0.75, 0.5), abs=0.03)
    assert view.quad("a") == [(20, 20), (60, 20), (60, 60), (20, 60)]  # the layer itself didn't move
