"""Project save/load as a document package: a folder named <name>.ctproj
containing project.json (metadata + transform params) and images/ (the raw,
untouched source photos). This is the prototype's stand-in for the spec's
"Custom document package with images + project metadata".

Layer images are stored RAW (pre-perspective-correction, pre-transform) so
reopening a project and re-rendering it reproduces the exact same result --
nothing is ever baked into pixels on save.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

import numpy as np
import cv2

from .models import Project
from .compositing import to_float_rgba, to_uint8_rgba

PROJECT_FILENAME = "project.json"
IMAGES_DIRNAME = "images"


@dataclass
class ProjectDocument:
    project: Project
    package_dir: Path | None = None
    images: dict[str, np.ndarray] = field(default_factory=dict)  # layer_id -> float32 RGBA

    def set_layer_image(self, layer_id: str, image_float_rgba: np.ndarray) -> None:
        self.images[layer_id] = image_float_rgba

    def get_layer_image(self, layer_id: str) -> np.ndarray | None:
        return self.images.get(layer_id)


def load_image_rgba(path: str | Path) -> np.ndarray:
    """Read an image file into float32 RGBA (0..1), any input channel count."""
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    if raw.ndim == 2:
        raw = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGRA)
    elif raw.shape[2] == 3:
        raw = cv2.cvtColor(raw, cv2.COLOR_BGR2BGRA)
    # raw is now BGRA uint8; convert to RGBA
    rgba = cv2.cvtColor(raw, cv2.COLOR_BGRA2RGBA)
    return to_float_rgba(rgba)


def write_image_rgba(path: str | Path, image_float_rgba: np.ndarray) -> None:
    rgba_uint8 = to_uint8_rgba(image_float_rgba)
    bgra = cv2.cvtColor(rgba_uint8, cv2.COLOR_RGBA2BGRA)
    ok = cv2.imwrite(str(path), bgra)
    if not ok:
        raise IOError(f"Could not write image: {path}")


def save_project(doc: ProjectDocument, path: str | Path) -> None:
    package_dir = Path(path)
    package_dir.mkdir(parents=True, exist_ok=True)
    images_dir = package_dir / IMAGES_DIRNAME
    images_dir.mkdir(exist_ok=True)

    for layer in doc.project.layers:
        image = doc.images.get(layer.id)
        if image is not None:
            write_image_rgba(images_dir / layer.image_filename, image)

    with open(package_dir / PROJECT_FILENAME, "w", encoding="utf-8") as f:
        json.dump(doc.project.to_dict(), f, indent=2)

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
    """Save in place if the project has already been saved once. Returns
    False (no-op) for a project that has never been saved to disk yet.
    """
    if doc.package_dir is None:
        return False
    save_project(doc, doc.package_dir)
    return True
