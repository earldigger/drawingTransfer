"""Renders the real Qt canvas scene offscreen and checks pixels, so blend
modes, placement, split view, grid and dragging are tested as drawn."""

import numpy as np
import pytest

from canvastransfer.compare import DisplayState
from canvastransfer.geometry import TransformMode
from canvastransfer.models import GridSettings, Layer, Project, CompareMode, BlendMode, new_id
from canvastransfer.project_io import ProjectDocument

SIZE = 100
FULL = [(0, 0), (SIZE, 0), (SIZE, SIZE), (0, SIZE)]


def solid_pixmap(rgb, w=10, h=10):
    from PySide6.QtGui import QColor, QPixmap

    pm = QPixmap(w, h)
    pm.fill(QColor(*rgb))
    return pm


def render(view):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    image = QImage(SIZE, SIZE, QImage.Format_RGB32)
    painter = QPainter(image)
    view.scene().render(painter, QRectF(0, 0, SIZE, SIZE), QRectF(0, 0, SIZE, SIZE))
    painter.end()
    return image


def rgb(image, x, y):
    c = image.pixelColor(x, y)
    return c.red(), c.green(), c.blue()


@pytest.fixture
def view(qapp):
    from canvastransfer.ui.canvas_view import CanvasView

    v = CanvasView()
    v.resize(500, 500)
    v.set_canvas_size(SIZE, SIZE)
    yield v
    v.deleteLater()


def entry(layer_id, color, quad=FULL, opacity=1.0, multiply=False, clip=None):
    from canvastransfer.ui.canvas_view import LayerEntry

    return LayerEntry(layer_id, solid_pixmap(color), quad, DisplayState(True, opacity, multiply, clip))


def close(a, b, tol=3):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_layer_is_placed_on_its_quad(view):
    view.show_layers([entry("a", (255, 0, 0), quad=[(20, 20), (60, 20), (60, 60), (20, 60)])], None)
    img = render(view)
    assert rgb(img, 40, 40) == (255, 0, 0)
    assert rgb(img, 10, 10) == (255, 255, 255)  # canvas shows through outside the quad


def test_multiply_darkens_layer_below(view):
    view.show_layers([entry("bottom", (255, 200, 0)), entry("top", (128, 128, 128), multiply=True)], None)
    assert close(rgb(render(view), 50, 50), (128, 100, 0))


def test_multiply_respects_opacity(view):
    view.show_layers([entry("bottom", (255, 0, 0)), entry("top", (0, 0, 0), opacity=0.5, multiply=True)], None)
    assert close(rgb(render(view), 50, 50), (128, 0, 0))


def test_normal_opacity_mixes(view):
    view.show_layers([entry("bottom", (0, 0, 0)), entry("top", (255, 255, 255), opacity=0.5)], None)
    assert close(rgb(render(view), 50, 50), (128, 128, 128))


def test_layers_are_clipped_to_canvas(view):
    view.show_layers([entry("big", (0, 0, 255), quad=[(-50, -50), (150, -50), (150, 150), (-50, 150)])], None)
    assert rgb(render(view), 50, 50) == (0, 0, 255)


def test_split_view_shows_a_left_and_b_right(view):
    view.show_layers([entry("a", (255, 0, 0), clip="left"), entry("b", (0, 0, 255), clip="right")], 0.5)
    img = render(view)
    assert rgb(img, 20, 50) == (255, 0, 0)
    assert rgb(img, 80, 50) == (0, 0, 255)


def test_grid_uses_chosen_color(view):
    view.set_grid(GridSettings(enabled=True, rows=2, columns=2, opacity=1.0, thickness_px=4, color=(0, 0, 255)))
    img = render(view)
    assert rgb(img, 50, 20) == (0, 0, 255)
    assert rgb(img, 20, 20) == (255, 255, 255)


def test_dragging_inside_box_moves_layer(view, qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    quad = [(20, 20), (60, 20), (60, 60), (20, 60)]
    view.show()
    view.show_layers([entry("a", (255, 0, 0), quad=quad)], None)
    view.set_active_layer("a")
    view.set_tool(True, TransformMode.UNIFORM)
    qapp.processEvents()

    committed = []
    view.quadCommitted.connect(lambda lid, q: committed.append((lid, q)))
    start = view.mapFromScene(QPointF(40, 40))
    end = view.mapFromScene(QPointF(50, 45))
    QTest.mousePress(view.viewport(), Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseRelease(view.viewport(), Qt.LeftButton, Qt.NoModifier, end)

    assert committed and committed[0][0] == "a"
    moved = committed[0][1]
    dx, dy = moved[0][0] - 20, moved[0][1] - 20
    assert 8 < dx < 12 and 3 < dy < 7


def test_corner_and_rotation_handles_are_hit(view, qapp):
    from PySide6.QtCore import QPointF

    quad = [(20, 20), (60, 20), (60, 60), (20, 60)]
    view.show()
    view.show_layers([entry("a", (255, 0, 0), quad=quad)], None)
    view.set_active_layer("a")
    view.set_tool(True, TransformMode.UNIFORM)
    qapp.processEvents()

    assert view._hit(view.mapFromScene(QPointF(60, 60))) == ("corner", 2)
    assert view._hit(view.mapFromScene(QPointF(40, 20))) == ("edge", 0)
    assert view._hit(view.mapFromScene(QPointF(40, 40))) == ("move",)
    top = view.mapFromScene(QPointF(40, 20))
    from PySide6.QtCore import QPoint

    assert view._hit(QPoint(top.x(), top.y() - 34)) == ("rotate",)


def test_no_handles_when_tool_off(view, qapp):
    from PySide6.QtCore import QPointF

    view.show_layers([entry("a", (255, 0, 0))], None)
    view.set_active_layer("a")
    view.set_tool(False, TransformMode.UNIFORM)
    assert view._hit(view.mapFromScene(QPointF(50, 50))) is None


def make_window_with_layers(qapp, *sizes):
    from canvastransfer.ui.main_window import MainWindow

    project = Project(name="T", canvas_width=10, canvas_height=10)
    doc = ProjectDocument(project)
    layers = []
    for i, (w, h) in enumerate(sizes):
        layer = Layer(id=new_id("l"), name=f"L{i}", image_filename=f"{i}.png")
        img = np.zeros((h, w, 4), dtype=np.uint8)
        img[..., :3] = 100
        img[..., 3] = 255
        doc.set_layer_image(layer.id, img)
        project.add_layer(layer)
        layers.append(layer)
    window = MainWindow()
    window._set_document(doc)
    return window, layers


def test_imported_image_is_fitted_not_cropped(qapp):
    window, (layer,) = make_window_with_layers(qapp, (4000, 1000))
    xs = [p[0] for p in layer.quad]
    ys = [p[1] for p in layer.quad]
    assert min(xs) >= 0 and max(xs) <= 1 and min(ys) >= 0 and max(ys) <= 1
    assert max(xs) - min(xs) == pytest.approx(1.0)  # full width used
    window.deleteLater()


def test_contrast_and_invert_change_displayed_pixmap(qapp):
    window, (layer,) = make_window_with_layers(qapp, (20, 20))
    item = window.canvas_view._items[layer.id]

    def center_gray():
        return item.pixmap().toImage().pixelColor(10, 10).red()

    assert center_gray() == 100
    window._set_layer_attr(layer.id, "invert", True)
    assert center_gray() == 155
    window._set_layer_attr(layer.id, "contrast", 0.5)
    assert center_gray() > 155
    window.deleteLater()


def test_blink_a_only_toggles_just_layer_a(qapp):
    window, (canvas_layer, drawing) = make_window_with_layers(qapp, (20, 20), (20, 20))
    project = window.doc.project
    project.compare_mode = CompareMode.BLINK_A
    project.compare_layer_a = drawing.id
    window._refresh_canvas()
    items = window.canvas_view._items

    window._blink_on = True
    window._on_blink_tick()
    assert not items[drawing.id].isVisible() and items[canvas_layer.id].isVisible()
    window._on_blink_tick()
    assert items[drawing.id].isVisible() and items[canvas_layer.id].isVisible()
    window.deleteLater()


def test_flip_mirrors_active_layer_quad(qapp):
    window, (layer,) = make_window_with_layers(qapp, (20, 10))
    before = list(layer.quad)
    window._flip(horizontal=True)
    assert layer.quad[0] == before[1] and layer.quad[1] == before[0]
    window._fit_active()
    assert layer.quad == before
    window.deleteLater()
