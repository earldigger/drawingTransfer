"""The folder new projects are saved in as soon as they are created, so they
autosave from the start (as iPhone and iPad apps do). By default
Dropbox/Canvas Transfer/Projects, next to the paint library; without
Dropbox, Documents/Canvas Transfer Projects. Changeable; the choice is
remembered in a pointer file in the app's data folder."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from .library_location import DROPBOX_SUBFOLDER, data_dir, dropbox_folder

POINTER_FILE = "projects_location.json"
PROJECTS_SUBFOLDER = "Projects"
PROJECT_SUFFIX = ".ctproj"


def default_projects_folder() -> Path:
    if os.environ.get("CANVASTRANSFER_DATA_DIR"):  # tests: stay inside their own folder
        return data_dir() / PROJECTS_SUBFOLDER
    dropbox = dropbox_folder()
    if dropbox is not None:
        return dropbox / DROPBOX_SUBFOLDER / PROJECTS_SUBFOLDER
    return Path.home() / "Documents" / "Canvas Transfer Projects"


def projects_folder() -> Path:
    try:
        chosen = json.loads((data_dir() / POINTER_FILE).read_text(encoding="utf-8")).get("path")
        if chosen:
            return Path(chosen)
    except (OSError, ValueError):
        pass
    return default_projects_folder()


def set_projects_folder(path: Path) -> None:
    data_dir().mkdir(parents=True, exist_ok=True)
    (data_dir() / POINTER_FILE).write_text(json.dumps({"path": str(path)}, indent=1), encoding="utf-8")


def safe_name(name: str) -> str:
    """A project name usable as a folder name on Mac, Windows and Dropbox."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", name).strip(" .")
    return cleaned[:80] or "Untitled Project"


def new_project_path(name: str, folder: Path | None = None) -> Path:
    """<folder>/<name>.ctproj, numbered ("Name 2.ctproj") if taken."""
    folder = Path(folder or projects_folder())
    base = safe_name(name)
    candidate = folder / f"{base}{PROJECT_SUFFIX}"
    n = 2
    while candidate.exists():
        candidate = folder / f"{base} {n}{PROJECT_SUFFIX}"
        n += 1
    return candidate


def choose_projects_folder(parent) -> Path | None:
    current = projects_folder()
    start = current if current.is_dir() else (dropbox_folder() or Path.home())
    folder = QFileDialog.getExistingDirectory(parent, "Folder for new projects (e.g. in Dropbox)", str(start))
    if not folder:
        return None
    folder = Path(folder)
    dropbox = dropbox_folder()
    if dropbox and folder.resolve() == dropbox.resolve():
        folder = folder / DROPBOX_SUBFOLDER / PROJECTS_SUBFOLDER  # keep the Dropbox top level tidy
    return folder
