"""Project save/load as a document package: a folder named <name>.ctproj
containing project.json (metadata + layer placement) and images/ (the raw,
untouched source photos). Stand-in for the spec's "custom document package
with images + project metadata".

Source images never change after import, so each is written once; saves
after that only rewrite project.json, which keeps autosave cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

import numpy as np
import cv2

from .models import Project

PROJECT_FILENAME = "project.json"
IMAGES_DIRNAME = "images"


@dataclass
class ProjectDocument:
    project: Project
    package_dir: Path | None = None
    images: dict[str, np.ndarray] = field(default_factory=dict)  # layer_id -> uint8 RGBA

    def set_layer_image(self, layer_id: str, image_rgba: np.ndarray) -> None:
        self.images[layer_id] = image_rgba

    def get_layer_image(self, layer_id: str) -> np.ndarray | None:
        return self.images.get(layer_id)


def _to_uint8(raw: np.ndarray) -> np.ndarray:
    if raw.dtype == np.uint16:
        return (raw >> 8).astype(np.uint8)
    if raw.dtype != np.uint8:
        return np.clip(raw, 0, 255).astype(np.uint8)
    return raw


def load_image_rgba(path: str | Path) -> np.ndarray:
    """Read an image file as uint8 RGBA. Phone photos are rotated upright
    using their EXIF orientation tag (IMREAD_UNCHANGED would ignore it), and
    images that carry transparency keep it.
    """
    path = str(path)
    unchanged = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if unchanged is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    if unchanged.ndim == 3 and unchanged.shape[2] == 4:
        return cv2.cvtColor(_to_uint8(unchanged), cv2.COLOR_BGRA2RGBA)
    color = cv2.imread(path, cv2.IMREAD_COLOR)
    return cv2.cvtColor(_to_uint8(color), cv2.COLOR_BGR2RGBA)


def write_image_rgba(path: str | Path, image_rgba: np.ndarray) -> None:
    if not cv2.imwrite(str(path), cv2.cvtColor(image_rgba, cv2.COLOR_RGBA2BGRA)):
        raise IOError(f"Could not write image: {path}")


def save_project(doc: ProjectDocument, path: str | Path) -> None:
    package_dir = Path(path)
    images_dir = package_dir / IMAGES_DIRNAME
    images_dir.mkdir(parents=True, exist_ok=True)

    referenced = set()
    for layer in doc.project.layers:
        referenced.add(layer.image_filename)
        image = doc.images.get(layer.id)
        target = images_dir / layer.image_filename
        if image is not None and not target.exists():
            write_image_rgba(target, image)

    for existing in images_dir.iterdir():
        if existing.is_file() and existing.name not in referenced:
            existing.unlink()  # image of a deleted layer

    tmp = package_dir / (PROJECT_FILENAME + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc.project.to_dict(), f, indent=2)
    tmp.replace(package_dir / PROJECT_FILENAME)

    doc.package_dir = package_dir


def load_project(path: str | Path) -> ProjectDocument:
    package_dir = Path(path)
    with open(package_dir / PROJECT_FILENAME, "r", encoding="utf-8") as f:
        project = Project.from_dict(json.load(f))

    images_dir = package_dir / IMAGES_DIRNAME
    images: dict[str, np.ndarray] = {}
    for layer in project.layers:
        image_path = images_dir / layer.image_filename
        if image_path.exists():
            images[layer.id] = load_image_rgba(image_path)

    return ProjectDocument(project=project, package_dir=package_dir, images=images)


def autosave(doc: ProjectDocument) -> bool:
    """Save in place if the project has been saved once; otherwise no-op."""
    if doc.package_dir is None:
        return False
    save_project(doc, doc.package_dir)
    return True
