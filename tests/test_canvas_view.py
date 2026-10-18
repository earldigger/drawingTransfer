"""Renders the real canvas compositor offscreen and checks pixels, so blend
modes, placement, split view, grid and dragging are tested as drawn."""

import pytest

from canvastransfer.compare import DisplayState
from canvastransfer.geometry import TransformMode
from canvastransfer.models import BlendMode, CompareMode, GridSettings

SIZE = 100
FULL = [(0, 0), (SIZE, 0), (SIZE, SIZE), (0, SIZE)]


def solid_pixmap(rgb, w=10, h=10):
    from PySide6.QtGui import QColor, QPixmap

    pm = QPixmap(w, h)
    pm.fill(QColor(*rgb))
    return pm


def render(view):
    return view.render_canvas_image()


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


def entry(layer_id, color, quad=FULL, opacity=1.0, blend=BlendMode.NORMAL, clip=None):
    from canvastransfer.ui.canvas_view import LayerEntry

    return LayerEntry(layer_id, solid_pixmap(color), quad, DisplayState(True, opacity, blend, clip))


def close(a, b, tol=3):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_layer_is_placed_on_its_quad(view):
    view.show_layers([entry("a", (255, 0, 0), quad=[(20, 20), (60, 20), (60, 60), (20, 60)])], None)
    img = render(view)
    assert rgb(img, 40, 40) == (255, 0, 0)
    assert rgb(img, 10, 10) == (255, 255, 255)  # canvas shows through outside the quad


def test_multiply_darkens_layer_below(view):
    view.show_layers([entry("bottom", (255, 200, 0)), entry("top", (128, 128, 128), blend=BlendMode.MULTIPLY)], None)
    assert close(rgb(render(view), 50, 50), (128, 100, 0))


def test_multiply_respects_opacity(view):
    view.show_layers([entry("bottom", (255, 0, 0)), entry("top", (0, 0, 0), opacity=0.5, blend=BlendMode.MULTIPLY)], None)
    assert close(rgb(render(view), 50, 50), (128, 0, 0))


def test_normal_opacity_mixes(view):
    view.show_layers([entry("bottom", (0, 0, 0)), entry("top", (255, 255, 255), opacity=0.5)], None)
    assert close(rgb(render(view), 50, 50), (128, 128, 128))


def test_screen_lightens_layer_below(view):
    view.show_layers([entry("bottom", (100, 200, 0)), entry("top", (128, 128, 128), blend=BlendMode.SCREEN)], None)
    # screen = 1 - (1-a)(1-b)
    assert close(rgb(render(view), 50, 50), (178, 227, 128))


def test_screen_respects_opacity(view):
    view.show_layers([entry("bottom", (0, 0, 0)), entry("top", (255, 255, 255), opacity=0.5, blend=BlendMode.SCREEN)], None)
    assert close(rgb(render(view), 50, 50), (128, 128, 128))


def test_linear_light_formula(view):
    # result = base + 2*blend - 255, clamped
    view.show_layers([entry("bottom", (100, 100, 220)), entry("top", (178, 64, 200), blend=BlendMode.LINEAR_LIGHT)], None)
    assert close(rgb(render(view), 50, 50), (201, 0, 255))


def test_linear_light_mid_gray_is_neutral(view):
    view.show_layers([entry("bottom", (30, 140, 230)), entry("top", (128, 128, 128), blend=BlendMode.LINEAR_LIGHT)], None)
    assert close(rgb(render(view), 50, 50), (31, 141, 231))


def test_linear_light_partial_opacity_mixes_with_clamped_result(view):
    # white paper over a light canvas at 50%: halfway to white, not blown out
    view.show_layers([entry("bottom", (217, 217, 217)), entry("top", (255, 255, 255), opacity=0.5, blend=BlendMode.LINEAR_LIGHT)], None)
    assert close(rgb(render(view), 50, 50), (236, 236, 236))


def test_linear_light_only_affects_its_quad(view):
    view.show_layers([entry("bottom", (100, 100, 100)),
                      entry("top", (255, 255, 255), quad=[(0, 0), (50, 0), (50, 100), (0, 100)], blend=BlendMode.LINEAR_LIGHT)], None)
    img = render(view)
    assert rgb(img, 25, 50) == (255, 255, 255)
    assert rgb(img, 75, 50) == (100, 100, 100)


def test_layers_above_linear_light_still_draw(view):
    view.show_layers([entry("bottom", (100, 100, 100)), entry("ll", (128, 128, 128), blend=BlendMode.LINEAR_LIGHT),
                      entry("top", (0, 0, 0), opacity=0.5)], None)
    assert close(rgb(render(view), 50, 50), (50, 50, 50))


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
    from tests.window_helpers import make_window_with_layers as make

    return make(*sizes)


def test_imported_image_is_fitted_not_cropped(qapp):
    window, (layer,) = make_window_with_layers(qapp, (4000, 1000))
    xs = [p[0] for p in layer.quad]
    ys = [p[1] for p in layer.quad]
    assert min(xs) >= 0 and max(xs) <= 1 and min(ys) >= 0 and max(ys) <= 1
    assert max(xs) - min(xs) == pytest.approx(1.0)  # full width used
    window.deleteLater()


def test_adjustment_controls_change_displayed_pixmap(qapp):
    window, (layer,) = make_window_with_layers(qapp, (20, 20))
    panel = window.layers_panel

    def center_gray():
        return window.canvas_view.entry(layer.id).pixmap.toImage().pixelColor(10, 10).red()

    assert center_gray() == 100
    panel.invert_check.setChecked(True)
    assert center_gray() == 155
    panel.black.slider.setValue(60)  # (155 - 60) / (255 - 60) -> darker
    assert center_gray() == 124
    panel.levels_reset.click()
    panel.temperature.slider.setValue(100)
    assert window.canvas_view.entry(layer.id).pixmap.toImage().pixelColor(10, 10).red() > 155
    window.deleteLater()


def test_dark_point_cannot_pass_light_point(qapp):
    window, (layer,) = make_window_with_layers(qapp, (20, 20))
    panel = window.layers_panel
    panel.white.slider.setValue(120)
    panel.black.slider.setValue(200)
    adj = window.doc.project.get_layer(layer.id).adjustments
    assert adj.black < adj.white
    assert panel.black.slider.value() == adj.black
    window.deleteLater()


def test_blink_a_only_toggles_just_layer_a(qapp):
    window, (canvas_layer, drawing) = make_window_with_layers(qapp, (20, 20), (20, 20))
    project = window.doc.project
    project.compare_mode = CompareMode.BLINK_A
    project.compare_layer_a = drawing.id
    window._refresh_canvas()
    def visible(layer):
        return window.canvas_view.entry(layer.id).state.visible

    window._blink_on = True
    window._on_blink_tick()
    assert not visible(drawing) and visible(canvas_layer)
    window._on_blink_tick()
    assert visible(drawing) and visible(canvas_layer)
    window.deleteLater()


def test_flip_mirrors_active_layer_quad(qapp):
    window, (layer,) = make_window_with_layers(qapp, (20, 10))
    before = list(layer.quad)
    window._flip(horizontal=True)
    assert layer.quad[0] == before[1] and layer.quad[1] == before[0]
    window._fit_active()
    assert layer.quad == before
    window.deleteLater()


def test_blend_combo_offers_new_modes(qapp):
    window, (layer,) = make_window_with_layers(qapp, (20, 20))
    combo = window.layers_panel.blend_combo
    for mode in (BlendMode.SCREEN, BlendMode.LINEAR_LIGHT):
        combo.setCurrentIndex(combo.findData(mode.value))
        assert window.doc.project.get_layer(layer.id).blend_mode == mode
    window.deleteLater()


def test_on_screen_render_matches_with_linear_light(view, qapp):
    """The live viewport path (device-pixel buffer, scaled transform) also composites Linear Light."""
    view.show()
    view.show_layers([entry("bottom", (100, 100, 100)), entry("top", (255, 255, 255), blend=BlendMode.LINEAR_LIGHT)], None)
    qapp.processEvents()
    shot = view.grab().toImage()
    center = view.mapFromScene(50, 50)
    c = shot.pixelColor(center.x(), center.y())
    assert (c.red(), c.green(), c.blue()) == (255, 255, 255)


def test_color_number_box_and_slider_stay_in_sync(qapp):
    window, (layer,) = make_window_with_layers(qapp, (20, 20))
    tint = window.layers_panel.tint
    tint.spin.setValue(-35)  # typing a number moves the slider and applies it
    assert tint.slider.value() == -35
    assert window.doc.project.get_layer(layer.id).adjustments.tint == -0.35
    tint.slider.setValue(20)
    assert tint.spin.value() == 20
    window.layers_panel.color_reset.click()
    assert tint.spin.value() == 0 and window.doc.project.get_layer(layer.id).adjustments.tint == 0
    window.undo_action.trigger()
    assert tint.spin.value() == 20 and tint.slider.value() == 20  # panel follows undo
    window.deleteLater()
