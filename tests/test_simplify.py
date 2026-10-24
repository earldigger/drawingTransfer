"""Simplify (flat colors / values), a highlight color per swatch, and the
projects folder new projects are saved in."""

import json

import numpy as np
import pytest

from canvastransfer import color_study as cs
from canvastransfer.models import Layer, Project, SimplifySettings, Swatch, new_id
from canvastransfer.project_io import ProjectDocument, load_project, save_project

ORANGE, BLUE, BROWN = (230, 130, 60), (60, 90, 170), (120, 80, 50)


def three_bands(h=60, w=90, noise=0):
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[..., 3] = 255
    third = w // 3
    img[:, :third, :3], img[:, third:2 * third, :3], img[:, 2 * third:, :3] = ORANGE, BLUE, BROWN
    if noise:
        jitter = np.random.default_rng(0).integers(-noise, noise + 1, (h, w, 3))
        img[..., :3] = np.clip(img[..., :3].astype(int) + jitter, 0, 255)
    return img


# -- color math ------------------------------------------------------------------

def test_simplify_finds_the_main_colors():
    result = cs.simplify(three_bands(noise=8), 3, smoothing=2)
    assert len(result.colors) == 3 and sum(result.shares) == pytest.approx(1.0)
    found = sorted(result.colors)
    for want in sorted([ORANGE, BLUE, BROWN]):
        assert any(np.abs(np.array(f) - want).max() <= 8 for f in found), (want, found)
    assert len({tuple(p) for p in result.image[..., :3].reshape(-1, 3)}) == 3  # flat
    assert result.colors == sorted(result.colors, key=lambda c: cs.lab_d65(c)[0])  # darkest first


def test_simplify_values_are_grays_ordered_dark_to_light():
    result = cs.simplify(three_bands(), 3, smoothing=0, values=True)
    assert all(c[0] == c[1] == c[2] for c in result.colors)
    assert [c[0] for c in result.colors] == sorted(c[0] for c in result.colors)


def test_simplify_asks_for_more_colors_than_the_image_has():
    result = cs.simplify(three_bands(), 8, smoothing=0)
    assert len(result.colors) == 3 and np.unique(result.labels).tolist() == [0, 1, 2]


def test_simplify_keeps_transparency():
    img = three_bands()
    img[:10, :, 3] = 0
    result = cs.simplify(img, 3, smoothing=1)
    assert (result.labels[:10] == -1).all() and (result.image[:10, :, 3] == 0).all()
    assert sum(result.shares) == pytest.approx(1.0)


def test_simplify_is_repeatable():
    img = three_bands(noise=20)
    a, b = cs.simplify(img, 4, 2), cs.simplify(img, 4, 2)
    assert a.colors == b.colors and np.array_equal(a.labels, b.labels)


def test_region_points_sit_inside_each_color():
    result = cs.simplify(three_bands(), 3, smoothing=0)
    h, w = result.labels.shape
    for i, (u, v) in enumerate(cs.region_points(result.labels, 3)):
        assert result.labels[int(v * h), int(u * w)] == i


def test_similarity_labels_closest_swatch_wins():
    img = np.zeros((1, 3, 4), dtype=np.uint8)
    img[0, :, :3] = [(200, 0, 0), (190, 10, 10), (0, 0, 200)]
    img[..., 3] = 255
    labels = cs.similarity_labels(cs.lab_image(img), [(200, 0, 0), (185, 12, 12)], 15)
    assert labels.tolist() == [[0, 1, -1]]  # middle pixel is nearer the second swatch; blue matches none


def test_highlight_colors_are_distinct_and_repeat_after_eight():
    colors = [cs.highlight_color(i) for i in range(8)]
    assert len(set(colors)) == 8 and cs.highlight_color(8) == colors[0]
    labs = [cs.lab_d65(c) for c in colors]
    closest = min(np.linalg.norm(labs[i] - labs[j]) for i in range(8) for j in range(i + 1, 8))
    assert closest > 25  # easy to tell apart side by side


# -- through the window ---------------------------------------------------------------

@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("CANVASTRANSFER_DATA_DIR", str(tmp_path / "appdata"))
    from canvastransfer.ui.main_window import MainWindow

    project = Project(name="T", canvas_width=9, canvas_height=6)
    layer = Layer(id=new_id("l"), name="photo", image_filename="p.png")
    doc = ProjectDocument(project)
    doc.set_layer_image(layer.id, three_bands(120, 180, noise=6))
    project.add_layer(layer)
    w = MainWindow()
    w.resize(1300, 900)
    w.show()
    w._set_document(doc)
    qapp.processEvents()
    yield w, layer
    w.close()
    w.deleteLater()


def pixel(w, fx, fy):
    cw, ch = w._canvas_size
    c = w.canvas_view.render_canvas_image().pixelColor(round(cw * fx), round(ch * fy))
    return (c.red(), c.green(), c.blue())


def test_each_highlighted_swatch_has_its_own_color(window, qapp):
    w, layer = window
    w.doc.project.swatches += [Swatch(new_id("s"), layer.id, 0.15, 0.5, ORANGE, highlight=True),
                               Swatch(new_id("s"), layer.id, 0.5, 0.5, BLUE, highlight=True),
                               Swatch(new_id("s"), layer.id, 0.85, 0.5, BROWN)]
    w._refresh_color_study()
    assert pixel(w, 0.15, 0.5) == cs.highlight_color(0)
    assert pixel(w, 0.5, 0.5) == cs.highlight_color(1)
    r, g, b = pixel(w, 0.85, 0.5)
    assert r == g == b  # not highlighted: gray
    markers = {m.number: m.ring for m in w.canvas_view._markers}
    assert markers == {1: cs.highlight_color(0), 2: cs.highlight_color(1), 3: None}


def set_simplify(w, qapp, **kw):
    settings = SimplifySettings(enabled=True, **kw)
    w.color_panel.set_simplify(settings)
    w.color_panel._emit_simplify_now()
    qapp.processEvents()


def test_simplify_shows_flat_colors_and_palette(window, qapp):
    w, _ = window
    set_simplify(w, qapp, colors=3, smoothing=1)
    assert w.doc.project.simplify.enabled and w.doc.project.simplify.colors == 3
    strip = w.color_panel.simplify_palette.colors()
    assert len(strip) == 3
    seen = {pixel(w, fx, 0.5) for fx in (0.1, 0.2, 0.4, 0.55, 0.75, 0.9)}
    assert seen <= set(strip) and len(seen) == 3
    w.color_panel.simplify_check.setChecked(False)
    qapp.processEvents()
    assert not w.doc.project.simplify.enabled and w.color_panel.simplify_palette.colors() == []


def test_value_mode_and_its_own_count(window, qapp):
    w, _ = window
    set_simplify(w, qapp, values=True, value_steps=2, colors=9)
    assert w.color_panel.simplify_count.label.text() == "Values:"
    assert w.color_panel.simplify_count.slider.value() == 2
    r, g, b = pixel(w, 0.15, 0.5)
    assert r == g == b
    assert len(w.color_panel.simplify_palette.colors()) == 2


def test_slider_changes_wait_for_a_pause(window, qapp):
    from PySide6.QtTest import QTest

    w, _ = window
    set_simplify(w, qapp, colors=3)
    w.color_panel.simplify_count.slider.setValue(2)
    assert w.doc.project.simplify.colors == 3  # not yet
    for _ in range(60):  # applied after a short pause; allow a slow machine
        QTest.qWait(50)
        if w.doc.project.simplify.colors == 2:
            break
    assert w.doc.project.simplify.colors == 2


def test_picking_while_simplified_takes_the_flat_color(window, qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    w, _ = window
    set_simplify(w, qapp, colors=3)
    w.pick_action.setChecked(True)
    cw, ch = w._canvas_size
    QTest.mouseClick(w.canvas_view.viewport(), Qt.LeftButton, Qt.NoModifier,
                     w.canvas_view.mapFromScene(QPointF(cw * 0.15, ch * 0.5)))
    qapp.processEvents()
    assert w.doc.project.swatches[0].rgb in w.color_panel.simplify_palette.colors()


def test_add_simplified_colors_as_swatches_and_undo(window, qapp):
    w, layer = window
    set_simplify(w, qapp, colors=3)
    w.color_panel.simplify_add.click()
    swatches = w.doc.project.swatches
    assert sorted(s.rgb for s in swatches) == sorted(w.color_panel.simplify_palette.colors())
    for s in swatches:  # each marker sits on its own color
        assert pixel(w, s.u, s.v) == s.rgb
    w.color_panel.simplify_add.click()
    assert len(w.doc.project.swatches) == 3  # no duplicates
    w.undo_action.trigger()
    assert w.doc.project.swatches == [] and w.doc.project.simplify.enabled  # undo keeps the view


def test_highlight_on_simplified_image_matches_whole_regions(window, qapp):
    w, layer = window
    set_simplify(w, qapp, colors=3)
    w.color_panel.simplify_add.click()
    first = w.doc.project.swatches[0]
    first.highlight = True
    w._refresh_color_study()
    region = w.cache.simplified(w.doc, layer, w._canvas_size, w.doc.project.simplify.key())[0]
    assert pixel(w, first.u, first.v) == cs.highlight_color(0)
    assert region.shares[0] > 0


def test_simplify_follows_the_selected_layer(window, qapp):
    w, layer = window
    other = Layer(id=new_id("l"), name="second", image_filename="q.png")
    w.doc.set_layer_image(other.id, np.full((40, 40, 4), 255, dtype=np.uint8))
    w.doc.project.add_layer(other)
    w._refresh_all()
    set_simplify(w, qapp, colors=3)
    assert w._simplified(other) is not None and w._simplified(layer) is None
    w._on_layer_selected(layer.id)
    assert w._simplified(layer) is not None


def test_simplify_settings_saved_with_project(tmp_path):
    project = Project(name="S", canvas_width=4, canvas_height=4,
                      simplify=SimplifySettings(enabled=True, values=True, colors=6, value_steps=4, smoothing=3))
    save_project(ProjectDocument(project), tmp_path / "S.ctproj")
    loaded = load_project(tmp_path / "S.ctproj").project.simplify
    assert loaded == project.simplify
    assert Project.from_dict({"name": "old", "canvas_width": 1, "canvas_height": 1}).simplify == SimplifySettings()


# -- projects folder ---------------------------------------------------------------------

def test_new_project_is_saved_straight_away(window, tmp_path):
    from canvastransfer.ui import projects_folder as pf
    from canvastransfer.ui import recent_projects as rp

    w, _ = window
    w.create_project(Project(name="Harbor: dusk", canvas_width=12, canvas_height=9))
    path = pf.projects_folder() / "Harbor- dusk.ctproj"
    assert w.doc.package_dir == path and (path / "project.json").exists()
    assert rp.recent_projects()[0].path == path.resolve()
    w.create_project(Project(name="Harbor: dusk", canvas_width=12, canvas_height=9))
    assert w.doc.package_dir.name == "Harbor- dusk 2.ctproj"


def test_change_projects_folder(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from canvastransfer.ui import projects_folder as pf

    w, _ = window
    target = tmp_path / "Dropbox" / "Canvas Transfer" / "Projects"
    target.mkdir(parents=True)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(target)))
    w.change_projects_folder()
    assert pf.projects_folder() == target
    assert json.loads((tmp_path / "appdata" / pf.POINTER_FILE).read_text())["path"] == str(target)
    w.create_project(Project(name="Pier", canvas_width=5, canvas_height=5))
    assert (target / "Pier.ctproj" / "project.json").exists()
    assert str(target) in w.start_screen.folder_label.text()


@pytest.mark.parametrize("service", ["iCloud Drive", "Dropbox"])
def test_cloud_top_level_gets_subfolders(qapp, tmp_path, monkeypatch, service):
    from PySide6.QtWidgets import QFileDialog

    from canvastransfer.ui import library_location as loc
    from canvastransfer.ui import projects_folder as pf

    top = tmp_path / service
    top.mkdir()
    monkeypatch.setattr(loc, "icloud_folder", lambda: top if service == "iCloud Drive" else None)
    monkeypatch.setattr(loc, "dropbox_folder", lambda: top if service == "Dropbox" else None)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(top)))
    assert pf.choose_projects_folder(None) == top / "Canvas Transfer" / "Projects"
    assert loc.choose_folder(None) == top / "Canvas Transfer"


def test_default_folder_prefers_icloud_then_dropbox(monkeypatch, tmp_path):
    from canvastransfer.ui import library_location as loc
    from canvastransfer.ui import projects_folder as pf

    monkeypatch.delenv("CANVASTRANSFER_DATA_DIR")
    icloud, dropbox = tmp_path / "iCloud", tmp_path / "Dropbox"
    monkeypatch.setattr(loc, "icloud_folder", lambda: icloud)
    monkeypatch.setattr(loc, "dropbox_folder", lambda: dropbox)
    assert pf.default_projects_folder() == icloud / "Canvas Transfer" / "Projects"
    monkeypatch.setattr(loc, "icloud_folder", lambda: None)
    assert pf.default_projects_folder() == dropbox / "Canvas Transfer" / "Projects"
    monkeypatch.setattr(loc, "dropbox_folder", lambda: None)
    assert pf.default_projects_folder().name == "Canvas Transfer Projects"


def test_icloud_drive_location(monkeypatch, tmp_path):
    from canvastransfer.ui import library_location as loc

    monkeypatch.setattr(loc.Path, "home", staticmethod(lambda: tmp_path))
    assert loc.icloud_folder() is None
    drive = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    drive.mkdir(parents=True)
    assert loc.icloud_folder() == drive


def test_safe_names():
    from canvastransfer.ui.projects_folder import safe_name

    assert safe_name('a/b:c*?"<>|') == "a-b-c------"
    assert safe_name("  ..  ") == "Untitled Project"


# -- fixed value scale -------------------------------------------------------------------

def gray_bars(*grays, h=10, w=10):
    img = np.zeros((h, w * len(grays), 4), dtype=np.uint8)
    img[..., 3] = 255
    for i, g in enumerate(grays):
        img[:, i * w:(i + 1) * w, :3] = g
    return img


def test_value_scale_is_equal_lightness_steps():
    for steps in (3, 5, 9):
        lightness = [cs.lab_d65(c)[0] for c in cs.value_scale(steps)]
        want = [(i + 0.5) * 100 / steps for i in range(steps)]
        assert np.allclose(lightness, want, atol=0.6)


def test_fixed_scale_puts_each_value_in_its_band():
    # L* about 6, 38, 58, 81, 98 -> bands 0, 1, 2, 4, 4 of five
    result = cs.simplify(gray_bars(20, 90, 140, 200, 250), 5, smoothing=0, values=True, fixed_scale=True)
    assert result.colors == cs.value_scale(5)
    assert [round(x, 2) for x in result.shares] == [0.2, 0.2, 0.2, 0.0, 0.4]  # nothing in band 3


def test_fixed_scale_is_the_same_for_every_image():
    dark = cs.simplify(gray_bars(20, 40, 60), 5, 0, values=True, fixed_scale=True)
    light = cs.simplify(gray_bars(180, 220, 250), 5, 0, values=True, fixed_scale=True)
    assert dark.colors == light.colors
    assert dark.shares[3:] == [0.0, 0.0] and light.shares[:2] == [0.0, 0.0]
    fitted = cs.simplify(gray_bars(20, 40, 60), 3, 0, values=True)  # the fitted mode spreads over what's there
    assert len(fitted.colors) == 3 and fitted.colors != cs.value_scale(3)


def test_value_scale_mode_in_the_panel(window, qapp):
    w, _ = window
    panel = w.color_panel
    panel.simplify_check.setChecked(True)
    panel.simplify_mode.setCurrentIndex(panel.simplify_mode.findData("scale"))
    qapp.processEvents()
    st = w.doc.project.simplify
    assert st.values and st.fixed_scale and panel.simplify_count.label.text() == "Steps:"
    assert panel.simplify_palette.colors() == cs.value_scale(st.value_steps)
    assert pixel(w, 0.15, 0.5) in cs.value_scale(st.value_steps)
    panel.simplify_mode.setCurrentIndex(panel.simplify_mode.findData("values"))
    qapp.processEvents()
    assert w.doc.project.simplify.values and not w.doc.project.simplify.fixed_scale
    w.color_panel.set_simplify(SimplifySettings(enabled=True, values=True, fixed_scale=True))
    assert panel.simplify_mode.currentData() == "scale"
