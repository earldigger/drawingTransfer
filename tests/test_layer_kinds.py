"""Canvas photos and references: their default look, where they go in the
stack, what Compare picks by default, and adding them through the window."""

import cv2
import numpy as np
import pytest

from canvastransfer.compare import default_compare_layers
from canvastransfer.image_ops import auto_levels, default_look, has_default_look
from canvastransfer.models import Adjustments, BlendMode, Layer, LayerKind, Project, new_id

from tests.window_helpers import make_window_with_layers


def layer(kind, name="L"):
    return Layer(id=new_id("l"), name=name, image_filename=f"{name}.png", kind=kind)


def drawing_photo(paper=200, line=60):
    """Gray paper with a dark line, like a photographed pencil drawing."""
    img = np.full((40, 40, 4), paper, dtype=np.uint8)
    img[..., 3] = 255
    img[10:14, 5:35, :3] = line
    return img


# -- model ---------------------------------------------------------------------


def test_kind_round_trips_through_dict():
    for kind in LayerKind:
        assert Layer.from_dict(layer(kind).to_dict()).kind == kind


def test_projects_saved_before_kinds_get_one_from_fill_canvas():
    old_canvas = layer(LayerKind.CANVAS).to_dict()
    old_canvas.pop("kind")
    old_canvas["perspective_fill_canvas"] = True
    old_reference = layer(LayerKind.REFERENCE).to_dict()
    old_reference.pop("kind")
    assert Layer.from_dict(old_canvas).kind == LayerKind.CANVAS
    assert Layer.from_dict(old_reference).kind == LayerKind.REFERENCE


def test_references_stay_on_top_of_canvas_photos():
    project = Project(name="P", canvas_width=16, canvas_height=20)
    first_canvas, reference, second_canvas = layer(LayerKind.CANVAS, "c1"), layer(LayerKind.REFERENCE, "r"), layer(LayerKind.CANVAS, "c2")
    for l in (first_canvas, reference, second_canvas):
        project.add_layer(l)
    assert [l.name for l in project.layers] == ["c1", "c2", "r"]  # bottom to top
    assert project.active_layer_id == second_canvas.id


# -- default look ---------------------------------------------------------------


def test_auto_levels_turns_paper_white_and_lines_dark():
    assert auto_levels(drawing_photo(paper=200, line=60)) == (60, 200)


def test_auto_levels_leaves_a_flat_image_alone():
    flat = drawing_photo(paper=128, line=120)
    assert auto_levels(flat) == (0, 255)


def test_auto_levels_ignores_transparent_pixels():
    img = drawing_photo()
    img[20:, :, :3] = 255
    img[20:, :, 3] = 0
    assert auto_levels(img) == (60, 200)


def test_reference_starts_at_multiply_60_with_auto_levels():
    opacity, blend, adjustments = default_look(LayerKind.REFERENCE, drawing_photo())
    assert (opacity, blend) == (0.6, BlendMode.MULTIPLY)
    assert (adjustments.black, adjustments.white) == (60, 200)


def test_canvas_photo_starts_at_normal_100_without_levels():
    opacity, blend, adjustments = default_look(LayerKind.CANVAS, drawing_photo())
    assert (opacity, blend, adjustments) == (1.0, BlendMode.NORMAL, Adjustments())


def test_has_default_look_notices_any_change():
    image = drawing_photo()
    l = layer(LayerKind.REFERENCE)
    l.opacity, l.blend_mode, l.adjustments = default_look(LayerKind.REFERENCE, image)
    assert has_default_look(l, image)
    l.opacity = 0.4
    assert not has_default_look(l, image)


# -- compare defaults ------------------------------------------------------------


def test_compare_defaults_to_reference_and_newest_canvas_photo():
    project = Project(name="P", canvas_width=16, canvas_height=20)
    old, reference, new = layer(LayerKind.CANVAS, "old"), layer(LayerKind.REFERENCE, "ref"), layer(LayerKind.CANVAS, "new")
    for l in (old, reference, new):
        project.add_layer(l)
    assert default_compare_layers(project) == (reference.id, new.id)


def test_compare_defaults_without_a_canvas_photo_use_the_next_layer_down():
    project = Project(name="P", canvas_width=16, canvas_height=20)
    lower, upper = layer(LayerKind.REFERENCE, "lower"), layer(LayerKind.REFERENCE, "upper")
    for l in (lower, upper):
        project.add_layer(l)
    assert default_compare_layers(project) == (upper.id, lower.id)


# -- adding layers through the window ------------------------------------------------


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    path = tmp_path / "photo.png"
    cv2.imwrite(str(path), cv2.cvtColor(drawing_photo(), cv2.COLOR_RGBA2BGRA))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))
    w, _ = make_window_with_layers()
    yield w
    w.deleteLater()


class FakeCornersDialog:
    """Stands in for Adjust Corners: accepts with the chosen fill setting."""

    Accepted = 1
    fill = True

    def __init__(self, image, corners, fill_canvas, parent=None):
        h, w = image.shape[:2]
        from canvastransfer.models import PerspectiveCorners

        self._corners = PerspectiveCorners.default_for_image(w, h)

    def exec(self):
        return self.Accepted

    def result_corners(self):
        return self._corners

    def result_fill_canvas(self):
        return FakeCornersDialog.fill


def test_add_reference_goes_on_top_at_multiply_60_with_transform_on(window):
    window._add_layer(LayerKind.REFERENCE)
    added = window.doc.project.layers[-1]
    assert added.kind == LayerKind.REFERENCE and added.name.startswith("Reference · ")
    assert (added.opacity, added.blend_mode) == (0.6, BlendMode.MULTIPLY)
    assert (added.adjustments.black, added.adjustments.white) == (60, 200)
    assert window.transform_action.isChecked()


def test_add_canvas_photo_opens_corners_and_fills_the_canvas(window, monkeypatch):
    import canvastransfer.ui.main_window as mw

    monkeypatch.setattr(mw, "PerspectiveDialog", FakeCornersDialog)
    FakeCornersDialog.fill = True
    window._add_layer(LayerKind.REFERENCE)
    window.transform_action.setChecked(False)
    window._add_layer(LayerKind.CANVAS)
    canvas = window.doc.project.get_layer(window.doc.project.active_layer_id)
    assert canvas.kind == LayerKind.CANVAS and canvas.name.startswith("Canvas · ")
    assert (canvas.opacity, canvas.blend_mode, canvas.adjustments) == (1.0, BlendMode.NORMAL, Adjustments())
    assert canvas.perspective_corners is not None and canvas.perspective_fill_canvas
    assert window.doc.project.layers[-1].kind == LayerKind.REFERENCE  # reference stays on top
    assert not window.transform_action.isChecked()


def test_switching_to_reference_in_corners_takes_the_reference_look(window, monkeypatch):
    import canvastransfer.ui.main_window as mw

    monkeypatch.setattr(mw, "PerspectiveDialog", FakeCornersDialog)
    FakeCornersDialog.fill = False  # chose Reference in Adjust Corners
    window._add_layer(LayerKind.CANVAS)
    added = window.doc.project.layers[-1]
    assert added.kind == LayerKind.REFERENCE
    assert (added.opacity, added.blend_mode) == (0.6, BlendMode.MULTIPLY)


def test_switching_kind_keeps_a_look_changed_by_hand(window, monkeypatch):
    import canvastransfer.ui.main_window as mw

    window._add_layer(LayerKind.REFERENCE)
    added = window.doc.project.layers[-1]
    added.opacity = 0.35
    monkeypatch.setattr(mw, "PerspectiveDialog", FakeCornersDialog)
    FakeCornersDialog.fill = True
    window._on_perspective_correct(added.id)
    assert added.kind == LayerKind.CANVAS and added.opacity == 0.35
