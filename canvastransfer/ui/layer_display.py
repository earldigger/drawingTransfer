"""Builds and caches the pixmap each layer shows on the canvas.

Two cache levels: the geometry step (perspective correction + downscale,
slow) is redone only when the corners change; the adjustment step
(levels, color, invert) is redone when those controls change.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QPixmap

from ..image_ops import (
    MAX_DISPLAY_EDGE,
    apply_adjustments,
    capped_size,
    corrected_size,
    downscale_to_max,
    perspective_correct,
)
from ..models import Layer
from ..project_io import ProjectDocument
from .image_qt import rgba_to_qpixmap


class LayerDisplayCache:
    def __init__(self):
        self._base: dict[str, tuple[tuple, np.ndarray]] = {}
        self._pixmaps: dict[str, tuple[tuple, QPixmap]] = {}

    def clear(self) -> None:
        self._base.clear()
        self._pixmaps.clear()

    def forget(self, layer_id: str) -> None:
        self._base.pop(layer_id, None)
        self._pixmaps.pop(layer_id, None)

    def _geometry_key(self, layer: Layer, canvas_size: tuple[int, int]) -> tuple:
        corners = tuple(layer.perspective_corners.as_list()) if layer.perspective_corners else None
        fill = layer.perspective_fill_canvas and corners is not None
        return (corners, fill, canvas_size if fill else None)

    def base_image(self, doc: ProjectDocument, layer: Layer, canvas_size: tuple[int, int]) -> np.ndarray | None:
        raw = doc.get_layer_image(layer.id)
        if raw is None:
            return None
        key = self._geometry_key(layer, canvas_size)
        cached = self._base.get(layer.id)
        if cached and cached[0] == key:
            return cached[1]

        corners, fill, _ = key
        if corners is None:
            base = downscale_to_max(raw)
        else:
            w, h = canvas_size if fill else corrected_size(layer.perspective_corners)
            base = perspective_correct(raw, layer.perspective_corners, capped_size(w, h, MAX_DISPLAY_EDGE))
        self._base[layer.id] = (key, base)
        return base

    def pixmap(self, doc: ProjectDocument, layer: Layer, canvas_size: tuple[int, int]) -> QPixmap | None:
        base = self.base_image(doc, layer, canvas_size)
        if base is None:
            return None
        key = (self._geometry_key(layer, canvas_size), layer.adjustments)
        cached = self._pixmaps.get(layer.id)
        if cached and cached[0] == key:
            return cached[1]
        pixmap = rgba_to_qpixmap(apply_adjustments(base, layer.adjustments))
        self._pixmaps[layer.id] = (key, pixmap)
        return pixmap
