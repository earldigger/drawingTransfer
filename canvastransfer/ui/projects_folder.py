"""The folder new projects are saved in as soon as they are created, so they
autosave from the start (as iPhone and iPad apps do). By default
iCloud Drive/Canvas Transfer/Projects (Dropbox if iCloud Drive is off;
Documents/Canvas Transfer Projects without either). Changeable; the choice is
remembered in a pointer file in the app's data folder."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from .library_location import APP_SUBFOLDER, cloud_folder, data_dir, tidy_cloud_choice

POINTER_FILE = "projects_location.json"
PROJECTS_SUBFOLDER = "Projects"
PROJECT_SUFFIX = ".ctproj"


def default_projects_folder() -> Path:
    if os.environ.get("CANVASTRANSFER_DATA_DIR"):  # tests: stay inside their own folder
        return data_dir() / PROJECTS_SUBFOLDER
    cloud = cloud_folder()
    if cloud is not None:
        return cloud / APP_SUBFOLDER / PROJECTS_SUBFOLDER
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
    start = current if current.is_dir() else (cloud_folder() or Path.home())
    folder = QFileDialog.getExistingDirectory(parent, "Folder for new projects (e.g. in iCloud Drive)", str(start))
    return tidy_cloud_choice(Path(folder), PROJECTS_SUBFOLDER) if folder else None
