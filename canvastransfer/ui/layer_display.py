"""Builds and caches the pixmap each layer shows on the canvas.

Cache levels: the geometry step (perspective correction + downscale,
slow) is redone only when the corners change; the adjustment step
(levels, color, invert) when those controls change; the color-study
highlight when its swatches or tolerance change; the simplified version
when its settings change. Highlights and simplification are computed at
reduced size, which keeps their sliders responsive.
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
from .. import color_study
from ..models import Layer
from ..project_io import ProjectDocument
from .image_qt import rgba_to_qpixmap


HIGHLIGHT_MAX_EDGE = 1200
SIMPLIFY_MAX_EDGE = 800  # flat shapes need little detail, and this keeps the sliders quick


class LayerDisplayCache:
    def __init__(self):
        self._base: dict[str, tuple[tuple, np.ndarray]] = {}
        self._adjusted: dict[str, tuple[tuple, np.ndarray, QPixmap]] = {}
        self._lab: dict[str, tuple[tuple, np.ndarray, np.ndarray]] = {}
        self._highlights: dict[str, tuple[tuple, QPixmap]] = {}
        self._simplified: dict[str, tuple] = {}

    def _caches(self):
        return (self._base, self._adjusted, self._lab, self._highlights, self._simplified)

    def clear(self) -> None:
        for d in self._caches():
            d.clear()

    def forget(self, layer_id: str) -> None:
        for d in self._caches():
            d.pop(layer_id, None)

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

    def _adjusted_entry(self, doc: ProjectDocument, layer: Layer, canvas_size: tuple[int, int]):
        base = self.base_image(doc, layer, canvas_size)
        if base is None:
            return None
        key = (self._geometry_key(layer, canvas_size), layer.adjustments)
        cached = self._adjusted.get(layer.id)
        if cached and cached[0] == key:
            return cached
        image = apply_adjustments(base, layer.adjustments)
        entry = (key, image, rgba_to_qpixmap(image))
        self._adjusted[layer.id] = entry
        return entry

    def pixmap(self, doc: ProjectDocument, layer: Layer, canvas_size: tuple[int, int]) -> QPixmap | None:
        entry = self._adjusted_entry(doc, layer, canvas_size)
        return entry[2] if entry else None

    def adjusted_image(self, doc: ProjectDocument, layer: Layer, canvas_size: tuple[int, int]) -> np.ndarray | None:
        """The pixels the layer shows (after perspective + adjustments),
        which is what the color picker samples."""
        entry = self._adjusted_entry(doc, layer, canvas_size)
        return entry[1] if entry else None

    def _small(self, doc: ProjectDocument, layer: Layer, canvas_size: tuple[int, int]):
        """(adjust key, the adjusted image at highlight size, its Lab)."""
        entry = self._adjusted_entry(doc, layer, canvas_size)
        if entry is None:
            return None
        adjust_key, image, _ = entry
        cached = self._lab.get(layer.id)
        if not cached or cached[0] != adjust_key:
            small = downscale_to_max(image, HIGHLIGHT_MAX_EDGE)
            cached = (adjust_key, small, color_study.lab_image(small))
            self._lab[layer.id] = cached
        return cached

    def simplified(self, doc: ProjectDocument, layer: Layer, canvas_size: tuple[int, int], settings: tuple):
        """(Simplified, its pixmap, its Lab) for SimplifySettings.key()."""
        entry = self._adjusted_entry(doc, layer, canvas_size)
        if entry is None:
            return None
        key = (entry[0], settings)
        cached = self._simplified.get(layer.id)
        if cached and cached[0] == key:
            return cached[1:]
        count, smoothing, values, fixed_scale = settings
        result = color_study.simplify(downscale_to_max(entry[1], SIMPLIFY_MAX_EDGE), count, smoothing, values,
                                      fixed_scale)
        cached = (key, result, rgba_to_qpixmap(result.image), color_study.lab_image(result.image))
        self._simplified[layer.id] = cached
        return cached[1:]

    def highlight_pixmap(self, doc: ProjectDocument, layer: Layer, canvas_size: tuple[int, int],
                         colors: list[tuple[tuple, tuple]], tolerance: float,
                         simplify: tuple | None = None) -> QPixmap | None:
        """Similar areas of the layer, each (swatch color, highlight color)
        in its own highlight color over a gray copy. With `simplify`
        settings, matches against the simplified image the canvas shows."""
        if not colors:
            return None
        small = self._small(doc, layer, canvas_size)
        if small is None:
            return None
        adjust_key, image, lab = small
        if simplify is not None:
            result, _, lab = self.simplified(doc, layer, canvas_size, simplify)
            image = result.image
        key = (adjust_key, simplify, tuple(colors), round(float(tolerance), 2))
        cached = self._highlights.get(layer.id)
        if cached and cached[0] == key:
            return cached[1]
        labels = color_study.similarity_labels(lab, [c for c, _ in colors], tolerance)
        pixmap = rgba_to_qpixmap(color_study.highlight_overlay(image, labels, [h for _, h in colors]))
        self._highlights[layer.id] = (key, pixmap)
        return pixmap
