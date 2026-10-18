"""Composites the layer stack into an image (the screen, or a test/export
target). Normal, Multiply and Screen use Qt's own blend modes. Linear Light
has no Qt equivalent and can't be built from them exactly at partial
opacity, so it is computed from the pixels already drawn underneath.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF, QTransform

from ..geometry import Quad
from ..models import BlendMode, GridSettings

GHOST_OPACITY = 0.3
QT_MODES = {
    BlendMode.NORMAL: QPainter.CompositionMode_SourceOver,
    BlendMode.MULTIPLY: QPainter.CompositionMode_Multiply,
    BlendMode.SCREEN: QPainter.CompositionMode_Screen,
}


@dataclass
class RenderLayer:
    pixmap: QPixmap
    quad: Quad
    opacity: float
    blend: BlendMode
    clip: QRectF | None = None  # scene coords


def quad_transform(pixmap: QPixmap, quad: Quad) -> QTransform | None:
    """Projective transform mapping the pixmap's rectangle onto `quad`."""
    w, h = pixmap.width(), pixmap.height()
    if w == 0 or h == 0:
        return None
    source = QPolygonF([QPointF(0, 0), QPointF(w, 0), QPointF(w, h), QPointF(0, h)])
    target = QPolygonF([QPointF(x, y) for x, y in quad])
    transform = QTransform()
    return transform if QTransform.quadToQuad(source, target, transform) else None


def image_array(image: QImage) -> np.ndarray:
    """Writable (h, w, 4) uint8 view of a 32-bit QImage's pixels (B, G, R, A)."""
    h, w = image.height(), image.width()
    return np.frombuffer(image.bits(), np.uint8).reshape(h, image.bytesPerLine())[:, : w * 4].reshape(h, w, 4)


def _begin(painter: QPainter, image: QImage, smooth: bool) -> None:
    painter.begin(image)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, smooth)
    painter.setRenderHint(QPainter.Antialiasing, True)


def _clip_to(painter: QPainter, scene_to_target: QTransform, canvas: QRectF, clip: QRectF | None) -> None:
    painter.setTransform(scene_to_target)
    painter.setClipRect(canvas)
    if clip is not None:
        painter.setClipRect(clip, Qt.IntersectClip)


def _linear_light(target: QImage, scratch: QImage, layer: RenderLayer, layer_tf: QTransform,
                  scene_to_target: QTransform, canvas: QRectF, smooth: bool) -> None:
    """result = base + A * (clamp(base + 2*blend - 1) - base), A = alpha * opacity."""
    area = canvas if layer.clip is None else canvas.intersected(layer.clip)
    quad_bounds = QPolygonF([QPointF(x, y) for x, y in layer.quad]).boundingRect()
    box = scene_to_target.mapRect(area.intersected(quad_bounds)).toAlignedRect()
    box = box.intersected(target.rect())
    if box.isEmpty():
        return

    scratch.fill(Qt.transparent)
    p = QPainter()
    _begin(p, scratch, smooth)
    _clip_to(p, scene_to_target, canvas, layer.clip)
    p.setTransform(layer_tf)
    p.drawPixmap(0, 0, layer.pixmap)
    p.end()

    y0, y1, x0, x1 = box.top(), box.bottom() + 1, box.left(), box.right() + 1
    base_px = image_array(target)[y0:y1, x0:x1]
    blend_px = image_array(scratch)[y0:y1, x0:x1]
    base = np.ascontiguousarray(base_px[..., :3])
    blend = np.ascontiguousarray(blend_px[..., :3])
    full = cv2.addWeighted(base, 1.0, blend, 2.0, -255.0)  # saturating: clamp(base + 2b - 255)
    weight = blend_px[..., 3].astype(np.float32) * (layer.opacity / 255.0)
    base_px[..., :3] = cv2.blendLinear(full, base, weight, 1.0 - weight)


def render_canvas(
    target: QImage,
    scene_to_target: QTransform,
    canvas: QRectF,
    layers: list[RenderLayer],
    grid: GridSettings | None = None,
    split_x: float | None = None,
    ghost: RenderLayer | None = None,
    background: QColor = QColor(64, 64, 64),
    smooth: bool = True,
    scratch: QImage | None = None,
) -> None:
    """Draw everything into `target` (Format_ARGB32_Premultiplied).
    `layers` are bottom-to-top; `scratch` is reused between frames when given."""
    target.fill(background)
    p = QPainter()
    _begin(p, target, smooth)

    if ghost is not None and (tf := quad_transform(ghost.pixmap, ghost.quad)) is not None:
        # Drawn under the opaque canvas, so only the part outside it shows.
        p.setTransform(tf * scene_to_target)
        p.setOpacity(GHOST_OPACITY)
        p.drawPixmap(0, 0, ghost.pixmap)
        p.setOpacity(1.0)

    p.setTransform(scene_to_target)
    p.fillRect(canvas, Qt.white)

    for layer in layers:
        tf = quad_transform(layer.pixmap, layer.quad)
        if tf is None or layer.opacity <= 0:
            continue
        full_tf = tf * scene_to_target
        if layer.blend == BlendMode.LINEAR_LIGHT:
            p.end()
            if scratch is None or scratch.size() != target.size():
                scratch = QImage(target.size(), QImage.Format_ARGB32)
            _linear_light(target, scratch, layer, full_tf, scene_to_target, canvas, smooth)
            _begin(p, target, smooth)
            continue
        p.save()
        _clip_to(p, scene_to_target, canvas, layer.clip)
        p.setTransform(full_tf)
        p.setCompositionMode(QT_MODES[layer.blend])
        p.setOpacity(layer.opacity)
        p.drawPixmap(0, 0, layer.pixmap)
        p.restore()

    if grid is not None and grid.enabled and grid.rows >= 1 and grid.columns >= 1:
        _clip_to(p, scene_to_target, canvas, None)
        r, g, b = grid.color
        pen = QPen(QColor(r, g, b, round(255 * grid.opacity)), grid.thickness_px)
        pen.setCapStyle(Qt.FlatCap)
        p.setPen(pen)
        for i in range(1, grid.columns):
            x = canvas.left() + canvas.width() * i / grid.columns
            p.drawLine(QPointF(x, canvas.top()), QPointF(x, canvas.bottom()))
        for i in range(1, grid.rows):
            y = canvas.top() + canvas.height() * i / grid.rows
            p.drawLine(QPointF(canvas.left(), y), QPointF(canvas.right(), y))

    if split_x is not None:
        p.setTransform(scene_to_target)
        p.setClipping(False)
        pen = QPen(Qt.white, 2)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawLine(QPointF(split_x, canvas.top()), QPointF(split_x, canvas.bottom()))
    p.end()
