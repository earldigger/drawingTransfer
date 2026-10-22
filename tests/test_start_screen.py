"""Start screen: New / Open / recent projects with thumbnails, Close Project,
and the save prompt for never-saved work."""

import os
import time

import numpy as np
import pytest

from canvastransfer.models import Layer, Project, new_id
from canvastransfer.project_io import ProjectDocument, save_project
from canvastransfer.ui import recent_projects as rp


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CANVASTRANSFER_DATA_DIR", str(tmp_path / "appdata"))
    return tmp_path


def project_doc(name="Portrait", color=(200, 120, 60)):
    project = Project(name=name, canvas_width=10, canvas_height=8)
    layer = Layer(id=new_id("l"), name="photo", image_filename="p.png")
    img = np.zeros((80, 100, 4), dtype=np.uint8)
    img[...] = (*color, 255)
    doc = ProjectDocument(project)
    doc.set_layer_image(layer.id, img)
    project.add_layer(layer)
    return doc


def saved_project(folder, name="Portrait", color=(200, 120, 60)):
    doc = project_doc(name, color)
    path = folder / f"{name}.ctproj"
    save_project(doc, path)
    return path


@pytest.fixture
def window(qapp, data_dir):
    from canvastransfer.ui.main_window import MainWindow

    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    qapp.processEvents()
    yield w
    w.close()
    w.deleteLater()


# -- recents list ------------------------------------------------------------------

def test_recents_newest_first_without_duplicates(data_dir):
    a, b = saved_project(data_dir, "A"), saved_project(data_dir, "B")
    rp.add_recent(a, "A")
    rp.add_recent(b, "B")
    rp.add_recent(a, "A")
    assert [r.name for r in rp.recent_projects()] == ["A", "B"]


def test_recents_capped_and_removable(data_dir):
    paths = [saved_project(data_dir, f"P{i}") for i in range(rp.MAX_RECENTS + 3)]
    for i, p in enumerate(paths):
        rp.add_recent(p, f"P{i}")
    names = [r.name for r in rp.recent_projects()]
    assert len(names) == rp.MAX_RECENTS and names[0] == f"P{len(paths) - 1}"
    rp.remove_recent(paths[-1])
    assert rp.recent_projects()[0].name == f"P{len(paths) - 2}"


def test_missing_projects_hidden_but_kept(data_dir):
    path = saved_project(data_dir, "Gone")
    rp.add_recent(path, "Gone")
    os.rename(path, data_dir / "elsewhere")
    assert rp.recent_projects() == []
    assert [r.name for r in rp.recent_projects(include_missing=True)] == ["Gone"]
    os.rename(data_dir / "elsewhere", path)  # e.g. the drive is plugged back in
    assert [r.name for r in rp.recent_projects()] == ["Gone"]


def test_damaged_recents_file_is_ignored(data_dir):
    (data_dir / "appdata").mkdir()
    (data_dir / "appdata" / rp.RECENTS_FILE).write_text("{oops")
    assert rp.recent_projects() == []


# -- the window ------------------------------------------------------------------------

def test_opens_on_the_start_screen(window):
    assert window.stack.currentWidget() is window.start_screen
    assert not window.tool_bar.isVisible() and not window.side_dock.isVisible()
    assert not window.save_action.isEnabled() and not window.close_action.isEnabled()
    assert window.start_screen.empty_label.isVisible()


def test_recent_cards_open_the_project(window, data_dir, qapp):
    path = saved_project(data_dir, "Still life")
    rp.add_recent(path, "Still life")
    window.start_screen.refresh()
    lst = window.start_screen.recent_list
    assert lst.count() == 1 and lst.item(0).text().startswith("Still life\nToday")
    lst.itemClicked.emit(lst.item(0))
    qapp.processEvents()
    assert window.doc.project.name == "Still life"
    assert window.stack.currentWidget() is window.canvas_view
    assert window.tool_bar.isVisible() and window.side_dock.isVisible()


def test_save_as_adds_recent_with_thumbnail_and_close_returns(window, data_dir, qapp, monkeypatch):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QFileDialog

    window._set_document(project_doc("Orange", color=(230, 120, 30)))
    target = data_dir / "Orange.ctproj"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    window._save_project_as()
    thumb = QImage(str(target / rp.THUMBNAIL_FILE))
    assert not thumb.isNull() and max(thumb.width(), thumb.height()) == 480
    c = thumb.pixelColor(thumb.width() // 2, thumb.height() // 2)
    assert (c.red(), c.green(), c.blue()) == (230, 120, 30)  # the canvas, not a blank image
    assert [r.name for r in rp.recent_projects()] == ["Orange"]
    assert window.close_project()
    assert window.doc is None and window.stack.currentWidget() is window.start_screen
    assert window.start_screen.recent_list.count() == 1


def test_unsaved_project_prompt(window, data_dir, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from canvastransfer.ui.main_window import MainWindow

    window._set_document(project_doc("Sketch"))
    monkeypatch.setattr(MainWindow, "_ask_save_unsaved", lambda self, name: None)  # Cancel
    assert not window.close_project() and window.doc is not None
    monkeypatch.setattr(MainWindow, "_ask_save_unsaved", lambda self, name: "save")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))  # cancels Save As
    assert not window.close_project() and window.doc is not None
    target = data_dir / "Sketch.ctproj"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    assert window.close_project()
    assert (target / "project.json").exists() and rp.recent_projects()[0].name == "Sketch"


def test_empty_new_project_closes_without_asking(window, monkeypatch):
    from canvastransfer.ui.main_window import MainWindow

    asked = []
    monkeypatch.setattr(MainWindow, "_ask_save_unsaved", lambda self, name: asked.append(name))
    window._set_document(ProjectDocument(Project(name="Blank", canvas_width=5, canvas_height=5)))
    assert window.close_project() and asked == []


def test_missing_recent_offers_removal(window, data_dir, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    path = saved_project(data_dir, "Moved")
    rp.add_recent(path, "Moved")
    (path / "project.json").unlink()
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    window._open_recent(str(path))
    assert window.doc is None
    assert rp.recent_projects(include_missing=True) == []


def test_open_recent_menu(window, data_dir):
    for name in ("One", "Two"):
        rp.add_recent(saved_project(data_dir, name), name)
    window._fill_recent_menu()
    assert [a.text() for a in window.recent_menu.actions()] == ["Two", "One"]
    window.recent_menu.actions()[1].trigger()
    assert window.doc.project.name == "One"


def test_autosave_refreshes_thumbnail_at_most_every_few_seconds(window, data_dir, monkeypatch):
    from canvastransfer.ui import main_window as mw

    path = saved_project(data_dir, "Busy")
    window.open_project_path(path)
    thumb = path / rp.THUMBNAIL_FILE
    window._write_thumbnail(force=True)
    first = thumb.stat().st_mtime_ns
    time.sleep(0.02)
    window._autosave_now()
    assert thumb.stat().st_mtime_ns == first  # too soon
    monkeypatch.setattr(mw, "THUMBNAIL_INTERVAL_S", 0)
    window._autosave_now()
    assert thumb.stat().st_mtime_ns != first
