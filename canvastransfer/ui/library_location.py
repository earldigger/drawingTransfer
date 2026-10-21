"""Where the paint library file lives. By default in the app's data folder;
you can move it to any folder, such as Dropbox, so it is backed up and can
be shared between computers. The chosen location is remembered in a small
pointer file in the app's data folder."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QFileDialog, QMessageBox

from ..paints import PaintLibrary

LIBRARY_FILE = "paints.json"
POINTER_FILE = "library_location.json"
DROPBOX_SUBFOLDER = "Canvas Transfer"


def data_dir() -> Path:
    """The app's data folder (on a Mac: ~/Library/Application Support/Canvas
    Transfer). CANVASTRANSFER_DATA_DIR overrides it, which the tests use."""
    override = os.environ.get("CANVASTRANSFER_DATA_DIR")
    return Path(override) if override else Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))


def library_path() -> Path:
    pointer = data_dir() / POINTER_FILE
    try:
        chosen = json.loads(pointer.read_text(encoding="utf-8")).get("path")
        if chosen:
            return Path(chosen)
    except (OSError, ValueError):
        pass
    return data_dir() / LIBRARY_FILE


def set_library_path(path: Path) -> None:
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / POINTER_FILE).write_text(json.dumps({"path": str(path)}, indent=1), encoding="utf-8")


def dropbox_folder() -> Path | None:
    """The Dropbox folder on this computer, if there is one. Newer Dropbox
    versions on a Mac live in ~/Library/CloudStorage/Dropbox."""
    home = Path.home()
    cloud = home / "Library" / "CloudStorage"
    candidates = sorted(cloud.glob("Dropbox*")) if cloud.is_dir() else []
    candidates.append(home / "Dropbox")
    return next((c for c in candidates if c.is_dir()), None)


def ask_existing(parent, there: int, here: int) -> str | None:
    """'use', 'replace' or None (cancel) when the chosen folder already has a library."""
    box = QMessageBox(parent)
    box.setWindowTitle("Paint Library Location")
    box.setText(f"That folder already has a paint library with {there} paints.")
    box.setInformativeText(f"Use that library (your current {here} paints stay in the old place as a backup), "
                           "or replace it with your current library (it is first copied to a backup file)?")
    use = box.addButton("Use That Library", QMessageBox.AcceptRole)
    replace = box.addButton("Replace It", QMessageBox.DestructiveRole)
    box.addButton(QMessageBox.Cancel)
    box.exec()
    return {use: "use", replace: "replace"}.get(box.clickedButton())


def choose_folder(parent) -> Path | None:
    dropbox = dropbox_folder()
    start = dropbox / DROPBOX_SUBFOLDER if dropbox and (dropbox / DROPBOX_SUBFOLDER).is_dir() else (dropbox or Path.home())
    folder = QFileDialog.getExistingDirectory(parent, "Folder for your paint library (e.g. in Dropbox)", str(start))
    if not folder:
        return None
    folder = Path(folder)
    if dropbox and folder.resolve() == dropbox.resolve():
        folder = folder / DROPBOX_SUBFOLDER  # keep the Dropbox top level tidy
    return folder


def move_library(library: PaintLibrary, folder: Path, parent=None) -> bool:
    """Store the library in `folder` from now on. Returns False if cancelled."""
    target = Path(folder) / LIBRARY_FILE
    if library.path is not None and target.resolve() == Path(library.path).resolve():
        return False
    if target.exists():
        try:
            other = PaintLibrary.load(target)
        except (OSError, ValueError, TypeError, KeyError) as e:
            QMessageBox.warning(parent, "Paint Library Location", f"Couldn't read the library in that folder ({e}).")
            return False
        choice = ask_existing(parent, len(other.paints), len(library.paints))
        if choice is None:
            return False
        if choice == "use":
            library.replace_with(other)
        else:
            shutil.copy2(target, target.with_name(f"paints.backup-{time.strftime('%Y%m%d-%H%M%S')}.json"))
            library.move_to(target)
    else:
        library.move_to(target)
    set_library_path(target)
    return True
