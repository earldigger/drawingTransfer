"""Your edits survive re-imports; series and drying time; keeping the library
in another folder (Dropbox) and picking up changes synced from elsewhere."""

import json
from pathlib import Path

import numpy as np
import pytest

from canvastransfer.paints import Paint, PaintLibrary, parse_collection_html

FIXTURE = Path(__file__).parent / "fixtures" / "collection_sample.html"


def sample():
    return parse_collection_html(FIXTURE.read_text(encoding="utf-8"))[1]


def imported():
    lib = PaintLibrary()
    lib.merge(sample())
    return lib


def edit(paint, **values):
    before = paint.site_values()
    for k, v in values.items():
        setattr(paint, k, v)
    paint.note_edits(before)


def test_series_read_from_the_page():
    series = {p.name: p.series for p in sample()}
    assert series["Old Delft Blue"] == "C" and series["Light Ultramarine Blue"] == "2"
    assert series["Viridian"] == ""  # not every paint lists one


def test_lightfastness_read_as_the_site_shows_it():
    rating = {p.name: p.lightfastness for p in sample()}
    assert rating["Old Delft Blue"] == "I"  # the maker's own scale
    assert rating["Titanium White"] == "ASTM I"
    assert rating["Light Ultramarine Blue"] == "★★★" and rating["Anise"] == "★★☆"


def test_lightfastness_text_combines_stars_and_astm():
    from canvastransfer.paints import _lightfastness_text

    assert _lightfastness_text(["★★★", "ASTM:", "I"]) == "★★★ · ASTM I"
    assert _lightfastness_text(["ASTM:", "II"]) == "ASTM II"
    assert _lightfastness_text([]) == ""


def test_your_lightfastness_survives_reimport():
    lib = imported()
    anise = lib.get("m27hg")
    edit(anise, lightfastness="ASTM II")
    assert anise.edited == ["lightfastness"]
    report = lib.merge(sample())
    assert anise.lightfastness == "ASTM II"
    assert [(p.id, f) for p, f in report.kept] == [("m27hg", ["lightfastness"])]


def test_your_lab_survives_reimport_of_a_paint_without_site_data():
    lib = imported()
    anise = lib.get("m27hg")
    edit(anise, lab=(60.0, -20.0, 50.0), source="Entered by hand")
    assert anise.edited == ["lab"]
    report = lib.merge(sample())
    assert anise.lab == (60.0, -20.0, 50.0) and anise.source == "Entered by hand"
    assert report.kept == []  # the site has nothing to compare


def test_edits_kept_and_differences_reported():
    lib = imported()
    delft = lib.get("dyoq9")
    edit(delft, name="Delft Blue", lab=(6.0, 9.0, -20.0), drying="slow")
    assert delft.edited == ["name", "lab"]  # drying time is always yours, not a site field
    again = sample()
    next(p for p in again if p.id == "dyoq9").pigments = ["PB60", "PBk9"]  # the site changed something you didn't
    report = lib.merge(again)
    assert delft.name == "Delft Blue" and delft.lab == (6.0, 9.0, -20.0) and delft.drying == "slow"
    assert delft.pigments == ["PB60", "PBk9"]
    assert [(p.id, f) for p, f in report.kept] == [("dyoq9", ["name", "lab"])]


def test_editing_back_to_the_site_value_clears_the_mark():
    lib = imported()
    delft = lib.get("dyoq9")
    edit(delft, name="X")
    edit(delft, name="Old Delft Blue")
    assert delft.edited == []


def test_site_never_blanks_out_your_value():
    lib = imported()
    titanium = lib.get("gsjog")
    gone = sample()
    next(p for p in gone if p.id == "gsjog").series = ""
    lib.merge(gone)
    assert titanium.series == "1"


def test_revert_to_site_data():
    lib = imported()
    delft = lib.get("dyoq9")
    edit(delft, name="Mine", lab=(1.0, 2.0, 3.0), source="Entered by hand", drying="slow")
    delft.revert_to_site()
    assert delft.name == "Old Delft Blue" and delft.lab == pytest.approx((5.385, 9.614, -19.735))
    assert delft.source == "Chart" and delft.edited == [] and delft.drying == "slow"


def test_paints_imported_before_this_version_keep_their_differences():
    # a library saved by the previous version: no site snapshot, no edit marks
    lib = PaintLibrary([Paint.from_dict({k: v for k, v in p.to_dict().items() if k not in ("site", "edited")})
                        for p in sample()])
    anise = lib.get("m27hg")
    anise.lab = (60.0, -20.0, 50.0)  # pasted in the previous version
    report = lib.merge(sample())
    assert anise.lab == (60.0, -20.0, 50.0) and anise.edited == ["lab"]
    assert report.kept == []
    assert lib.get("dyoq9").edited == []  # unchanged paints are not marked


def test_manual_paints_are_never_marked_edited():
    p = Paint(id="manual-1", medium="oil", brand="B", name="N")
    edit(p, name="M")
    assert p.edited == []


def test_saved_and_loaded_with_new_fields(tmp_path):
    lib = imported()
    lib.path = tmp_path / "paints.json"
    edit(lib.get("dyoq9"), drying="3-5 days", name="Mine")
    lib.changed()
    loaded = PaintLibrary.load(tmp_path / "paints.json").get("dyoq9")
    assert (loaded.drying, loaded.series, loaded.edited) == ("3-5 days", "C", ["name"])
    assert loaded.site["name"] == "Old Delft Blue"


def test_library_notices_changes_from_elsewhere(tmp_path):
    path = tmp_path / "paints.json"
    mine = PaintLibrary(sample(), path=path)
    mine.changed()
    assert not mine.changed_on_disk()
    other = PaintLibrary.load(path)  # e.g. the same file on another computer, synced by Dropbox
    other.get("dyoq9").favorite = True
    import os
    import time

    time.sleep(0.01)
    other.changed()
    os.utime(path, ns=(time.time_ns(), time.time_ns()))
    assert mine.changed_on_disk()
    mine.replace_with(PaintLibrary.load(path))
    assert mine.get("dyoq9").favorite and not mine.changed_on_disk()


def test_saving_over_a_change_from_elsewhere_keeps_a_copy(tmp_path):
    import os
    import time

    path = tmp_path / "paints.json"
    mine = PaintLibrary(sample(), path=path)
    mine.changed()
    other = PaintLibrary.load(path)
    other.get("dyoq9").name = "Changed on the other Mac"
    other.changed()
    os.utime(path, ns=(time.time_ns() + 10**9, time.time_ns() + 10**9))
    mine.get("m27hg").favorite = True
    mine.changed()  # saved without reloading first
    copies = list(tmp_path.glob("paints.other-*.json"))
    assert len(copies) == 1 and "Changed on the other Mac" in copies[0].read_text()
    assert PaintLibrary.load(path).get("m27hg").favorite


# -- library location ----------------------------------------------------------

@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CANVASTRANSFER_DATA_DIR", str(tmp_path / "appdata"))
    return tmp_path


def test_move_library_to_an_empty_folder(qapp, data_dir):
    from canvastransfer.ui import library_location as loc

    assert loc.library_path() == data_dir / "appdata" / "paints.json"
    lib = PaintLibrary(sample(), path=loc.library_path())
    lib.changed()
    dropbox = data_dir / "Dropbox" / "Canvas Transfer"
    assert loc.move_library(lib, dropbox)
    assert lib.path == dropbox / "paints.json" and lib.path.exists()
    assert loc.library_path() == dropbox / "paints.json"  # remembered for next start
    assert (data_dir / "appdata" / "paints.json").exists()  # the old file stays as a backup
    assert not loc.move_library(lib, dropbox)  # already there


@pytest.mark.parametrize("choice", ["use", "replace", None])
def test_move_to_a_folder_that_already_has_a_library(qapp, data_dir, monkeypatch, choice):
    from canvastransfer.ui import library_location as loc

    folder = data_dir / "Dropbox"
    theirs = PaintLibrary([Paint(id="x", medium="oil", brand="B", name="From the other Mac")],
                          path=folder / "paints.json")
    theirs.changed()
    lib = PaintLibrary(sample(), path=data_dir / "appdata" / "paints.json")
    lib.changed()
    asked = []
    monkeypatch.setattr(loc, "ask_existing", lambda parent, there, here: asked.append((there, here)) or choice)
    moved = loc.move_library(lib, folder)
    assert asked == [(1, 8)]
    stored = json.loads((folder / "paints.json").read_text())
    if choice == "use":
        assert moved and [p.name for p in lib.paints] == ["From the other Mac"]
        assert len(stored["paints"]) == 1
    elif choice == "replace":
        assert moved and len(lib.paints) == 8 and len(stored["paints"]) == 8
        backups = list(folder.glob("paints.backup-*.json"))
        assert len(backups) == 1 and "From the other Mac" in backups[0].read_text()
    else:
        assert not moved and lib.path == data_dir / "appdata" / "paints.json"
        assert loc.library_path() == data_dir / "appdata" / "paints.json"


def test_choosing_the_dropbox_top_level_uses_a_subfolder(qapp, data_dir, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from canvastransfer.ui import library_location as loc

    dropbox = data_dir / "Dropbox"
    dropbox.mkdir()
    monkeypatch.setattr(loc, "dropbox_folder", lambda: dropbox)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dropbox)))
    assert loc.choose_folder(None) == dropbox / "Canvas Transfer"


# -- through the window ------------------------------------------------------------

@pytest.fixture
def window(qapp, data_dir, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from canvastransfer.models import Layer, Project, new_id
    from canvastransfer.project_io import ProjectDocument
    from canvastransfer.ui.main_window import MainWindow

    messages = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: messages.append(a[2])))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    project = Project(name="T", canvas_width=10, canvas_height=10)
    layer = Layer(id=new_id("l"), name="photo", image_filename="p.png")
    doc = ProjectDocument(project)
    doc.set_layer_image(layer.id, np.full((50, 50, 4), 200, dtype=np.uint8))
    project.add_layer(layer)
    w = MainWindow()
    w.show()
    w._set_document(doc)
    w.open_paint_library()
    w.library_dialog.import_page(str(FIXTURE))
    yield w, messages
    w.close()
    w.deleteLater()


def row(dialog, name):
    from canvastransfer.ui.paint_library import COL_NAME, EDITED_MARK

    for g in range(dialog.tree.topLevelItemCount()):
        group = dialog.tree.topLevelItem(g)
        for c in range(group.childCount()):
            if group.child(c).text(COL_NAME).replace(EDITED_MARK, "") == name:
                return group.child(c)
    raise KeyError(name)


def test_series_lightfast_drying_columns_and_edit_dialog(window):
    from canvastransfer.ui.paint_dialog import PaintDialog
    from canvastransfer.ui.paint_library import HEADERS
    from canvastransfer.ui.paint_library import COL_DRYING, COL_LIGHTFAST, COL_NAME, COL_SERIES, EDITED_MARK

    w, _ = window
    dlg = w.library_dialog
    item = row(dlg, "Old Delft Blue")
    assert (item.text(COL_SERIES), item.text(COL_LIGHTFAST), item.text(COL_DRYING)) == ("C", "I", "")
    assert HEADERS.count("Code") == 0
    delft = w.paint_library.get("dyoq9")
    d = PaintDialog(w.paint_library, delft)
    d.drying.setText("slow")
    d.result_paint()  # OK without touching the color
    assert delft.drying == "slow" and delft.edited == [] and delft.lab == pytest.approx((5.385, 9.614, -19.735))
    d = PaintDialog(w.paint_library, delft)
    assert d.lightfastness.currentText() == "I" and not hasattr(d, "code")
    d.color_text.setText("6 9 -20")
    d.series.setText("D")
    d.result_paint()
    assert delft.edited == ["series", "lab"] and delft.source == "Entered by hand"
    dlg._changed(delft.id)
    item = row(dlg, "Old Delft Blue")
    assert item.text(COL_NAME).endswith(EDITED_MARK) and "Edited in the app" in item.toolTip(COL_NAME)
    assert item.text(COL_SERIES) == "D" and item.text(COL_DRYING) == "slow"


def test_reimport_through_the_window_keeps_edits_and_reports(window):
    from canvastransfer.ui.paint_dialog import PaintDialog

    w, messages = window
    delft = w.paint_library.get("dyoq9")
    d = PaintDialog(w.paint_library, delft)
    d.color_text.setText("6 9 -20")
    d.result_paint()
    w.library_dialog.import_page(str(FIXTURE))
    assert delft.lab == (6.0, 9.0, -20.0)
    assert "Your edits were kept on 1 paints" in messages[-1]
    assert "Old Delft Blue: color (Lab)" in messages[-1]


def test_revert_button(window):
    w, _ = window
    dlg = w.library_dialog
    delft = w.paint_library.get("dyoq9")
    edit(delft, name="Mine")
    dlg.refresh(delft.id)
    dlg.tree.setCurrentItem(row(dlg, "Mine"))
    assert dlg.revert_button.isEnabled()
    dlg.revert_selected()
    assert delft.name == "Old Delft Blue" and not dlg.revert_button.isEnabled()


def test_window_reloads_library_changed_on_disk(window):
    import os
    import time

    w, _ = window
    other = PaintLibrary.load(w.paint_library.path)
    other.get("dyoq9").name = "Renamed elsewhere"
    other.changed()
    os.utime(other.path, ns=(time.time_ns() + 10**9, time.time_ns() + 10**9))
    assert w.reload_library_if_changed()
    assert w.paint_library.get("dyoq9").name == "Renamed elsewhere"
    assert row(w.library_dialog, "Renamed elsewhere") is not None
    assert not w.reload_library_if_changed()


def test_location_shown_in_library_window(window, data_dir):
    w, _ = window
    assert str(data_dir / "appdata" / "paints.json") in w.library_dialog.location_label.text()


def test_layer_visibility_checkbox(qapp, window):
    from PySide6.QtCore import Qt

    w, _ = window
    item = w.layers_panel.list_widget.item(0)
    item.setCheckState(Qt.Unchecked)
    qapp.processEvents()  # applied just after the click
    assert not w.doc.project.layers[0].visible
