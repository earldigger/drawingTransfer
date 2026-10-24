"""The recently opened or saved projects, newest first, kept in the app's
data folder. Projects that can't be found right now (an unplugged drive,
a cloud folder not downloaded yet) stay in the list but are not shown
until they are back."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .library_location import data_dir

RECENTS_FILE = "recent_projects.json"
MAX_RECENTS = 12
THUMBNAIL_FILE = "thumbnail.png"  # inside each .ctproj package


@dataclass
class Recent:
    path: Path
    name: str
    opened: float  # time.time()

    @property
    def thumbnail(self) -> Path:
        return self.path / THUMBNAIL_FILE

    @property
    def available(self) -> bool:
        return (self.path / "project.json").is_file()


def _file() -> Path:
    return data_dir() / RECENTS_FILE


def _read() -> list[Recent]:
    try:
        raw = json.loads(_file().read_text(encoding="utf-8"))
        return [Recent(Path(r["path"]), r.get("name", Path(r["path"]).stem), float(r.get("opened", 0)))
                for r in raw.get("projects", [])]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _write(recents: list[Recent]) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps({"projects": [{"path": str(r.path), "name": r.name, "opened": r.opened}
                                                for r in recents]}, indent=1), encoding="utf-8")


def recent_projects(include_missing: bool = False) -> list[Recent]:
    return [r for r in _read() if include_missing or r.available]


def add_recent(path: str | Path, name: str) -> None:
    path = Path(path).resolve()
    recents = [r for r in _read() if r.path.resolve() != path]
    recents.insert(0, Recent(path, name, time.time()))
    _write(recents[:MAX_RECENTS])


def remove_recent(path: str | Path) -> None:
    path = Path(path).resolve()
    _write([r for r in _read() if r.path.resolve() != path])
