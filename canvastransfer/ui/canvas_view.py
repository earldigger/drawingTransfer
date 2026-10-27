"""The canvas: composites every layer live (via canvas_render) and hosts
the Fresco-style transform tool (8 handles + rotation handle on the active
layer, drag inside to move), its crop mode (4 corners + 4 edges of the crop,
drag inside to slide it; the cut-off part shows faintly), and the color
picker with its swatch markers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap, QPolygonF, QTransform
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from ..compare import DisplayState
from ..geometry import (
    FULL_CROP,
    Quad,
    TransformMode,
    apply_drag,
    crop_corners,
    crop_edge_midpoints,
    drag_crop,
    edge_midpoints,
    point_in_quad,
    rotation_handle,
)
from ..models import BlendMode, GridSettings
from .canvas_render import RenderLayer, quad_transform, render_canvas

HANDLE_RADIUS_PX = 6
MARKER_RADIUS_PX = 11
HIT_RADIUS_PX = 12
ROTATE_OFFSET_PX = 34
ACCENT = QColor(30, 144, 255)


@dataclass
class Marker:
    swatch_id: str
    number: int
    layer_id: str
    u: float  # position as fractions of the layer image, so it follows the layer
    v: float
    rgb: tuple[int, int, int]
    selected: bool = False
    ring: tuple[int, int, int] | None = None  # highlight color while the swatch is highlighted


@dataclass
class LayerEntry:
    layer_id: str
    pixmap: QPixmap
    quad: Quad
    state: DisplayState
    crop: tuple[float, float, float, float] | None = None


class CanvasView(QGraphicsView):
    quadCommitted = Signal(str, object)  # layer_id, quad in canvas px
    cropCommitted = Signal(str, object)  # layer_id, crop as (left, top, right, bottom) fractions
    colorPicked = Signal(float, float)  # scene point clicked in pick mode
    pickHover = Signal(object)  # scene (x, y) under the cursor in pick mode, or None
    markerClicked = Signal(str)  # swatch id

    def __init__(self, parent=None):
        super().__init__(parent)
        # The scene only provides the coordinate system (canvas pixels);
        # all drawing happens in drawBackground/drawForeground.
        self.setScene(QGraphicsScene(self))
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)

        self._canvas = QRectF(0, 0, 1, 1)
        self._entries: list[LayerEntry] = []
        self._quads: dict[str, Quad] = {}
        self._crops: dict[str, tuple | None] = {}
        self._crop_mode = False
        self._grid: GridSettings | None = None
        self._split_fraction: float | None = None
        self._active_id: str | None = None
        self._tool_enabled = False
        self._mode = TransformMode.UNIFORM
        self._drag: tuple | None = None  # (handle, start point, start quad)
        self._buffer: QImage | None = None
        self._scratch: QImage | None = None
        self._overlays: list[tuple[str, QPixmap]] = []  # (layer id, highlight pixmap)
        self._markers: list[Marker] = []
        self._pick_enabled = False
        self._pick_radius_scene = 0.0
        self._hover: QPointF | None = None

    # -- configuration ------------------------------------------------

    def set_canvas_size(self, width: int, height: int) -> None:
        self._canvas = QRectF(0, 0, width, height)
        self.scene().setSceneRect(self._canvas.adjusted(-20000, -20000, 20000, 20000))
        self.refit()

    def set_grid(self, grid: GridSettings) -> None:
        self._grid = grid
        self.viewport().update()

    def show_layers(self, entries: list[LayerEntry], split_fraction: float | None,
                    overlays: list[tuple[str, QPixmap]] | None = None) -> None:
        """Display layers bottom-to-top as described by `entries`."""
        dragging = self._drag_layer()
        self._entries = list(entries)
        for entry in entries:
            if entry.layer_id != dragging:
                self._quads[entry.layer_id] = list(entry.quad)
                self._crops[entry.layer_id] = entry.crop
        wanted = {e.layer_id for e in entries}
        self._quads = {k: v for k, v in self._quads.items() if k in wanted}
        self._crops = {k: v for k, v in self._crops.items() if k in wanted}
        self._split_fraction = split_fraction
        self._overlays = list(overlays or [])
        self.viewport().update()

    def entry(self, layer_id: str) -> LayerEntry | None:
        return next((e for e in self._entries if e.layer_id == layer_id), None)

    def set_active_layer(self, layer_id: str | None) -> None:
        if layer_id != self._active_id:
            self._active_id = layer_id
            if self._tool_enabled:
                self.refit()
            self.viewport().update()

    def set_tool(self, enabled: bool, mode: TransformMode) -> None:
        turned_on = enabled and not self._tool_enabled
        self._tool_enabled = enabled
        self._mode = mode
        if turned_on:
            self.refit()
        self.viewport().update()

    def set_crop_mode(self, enabled: bool) -> None:
        """While the transform tool is on: crop handles instead of transform handles."""
        self._crop_mode = enabled
        self.viewport().update()

    def quad(self, layer_id: str) -> Quad | None:
        return self._quads.get(layer_id)

    def crop(self, layer_id: str) -> tuple | None:
        return self._crops.get(layer_id)

    def _layer_transform(self, layer_id: str) -> QTransform | None:
        entry = self.entry(layer_id)
        return quad_transform(entry.pixmap, self._quads[layer_id]) if entry else None

    def _uv_to_scene(self, layer_id: str, uv) -> QPointF:
        entry = self.entry(layer_id)
        return self._layer_transform(layer_id).map(QPointF(uv[0] * entry.pixmap.width(), uv[1] * entry.pixmap.height()))

    def _scene_to_uv(self, layer_id: str, scene: QPointF) -> tuple[float, float] | None:
        entry = self.entry(layer_id)
        tf = self._layer_transform(layer_id)
        inverse, ok = tf.inverted() if tf is not None else (None, False)
        if not ok:
            return None
        p = inverse.map(scene)
        return p.x() / entry.pixmap.width(), p.y() / entry.pixmap.height()

    # -- rendering ----------------------------------------------------------

    def _render_layers(self) -> list[RenderLayer]:
        split_x = None if self._split_fraction is None else self._canvas.width() * self._split_fraction
        layers = []
        for e in self._entries:
            if not e.state.visible:
                continue
            clip = None
            if e.state.clip is not None and split_x is not None:
                c = self._canvas
                clip = (QRectF(c.left(), c.top(), split_x - c.left(), c.height()) if e.state.clip == "left"
                        else QRectF(split_x, c.top(), c.right() - split_x, c.height()))
            layers.append(RenderLayer(e.pixmap, self._quads[e.layer_id], e.state.opacity, e.state.blend, clip,
                                      self._crops.get(e.layer_id)))
        for layer_id, pixmap in self._overlays:
            entry = self.entry(layer_id)
            if entry is not None and entry.state.visible:
                layers.append(RenderLayer(pixmap, self._quads[layer_id], 1.0, BlendMode.NORMAL,
                                          crop=self._crops.get(layer_id)))
        return layers

    def set_markers(self, markers: list[Marker]) -> None:
        self._markers = list(markers)
        self.viewport().update()

    def set_pick(self, enabled: bool, radius_scene: float = 0.0) -> None:
        self._pick_enabled = enabled
        self._pick_radius_scene = radius_scene
        if enabled:
            self.viewport().setCursor(Qt.CrossCursor)
        else:
            self._hover = None
            self.viewport().unsetCursor()
        self.viewport().update()

    def layer_point(self, layer_id: str, scene_x: float, scene_y: float) -> tuple[float, float] | None:
        """Scene point -> pixel position in the layer's displayed image."""
        entry = self.entry(layer_id)
        tf = quad_transform(entry.pixmap, self._quads[layer_id]) if entry else None
        if tf is None:
            return None
        inverse, ok = tf.inverted()
        if not ok:
            return None
        p = inverse.map(QPointF(scene_x, scene_y))
        return p.x(), p.y()

    def _marker_point(self, m: Marker) -> QPointF | None:
        entry = self.entry(m.layer_id)
        if entry is None or not entry.state.visible:
            return None
        tf = quad_transform(entry.pixmap, self._quads[m.layer_id])
        if tf is None:
            return None
        return tf.map(QPointF(m.u * entry.pixmap.width(), m.v * entry.pixmap.height()))

    def _marker_at(self, view_pos) -> Marker | None:
        for m in reversed(self._markers):
            point = self._marker_point(m)
            if point is None:
                continue
            v = self.mapFromScene(point)
            if math.hypot(v.x() - view_pos.x(), v.y() - view_pos.y()) <= MARKER_RADIUS_PX:
                return m
        return None

    def _ghost(self) -> RenderLayer | None:
        if not self._active_editable():
            return None
        e = self.entry(self._active_id)
        return RenderLayer(e.pixmap, self._quads[e.layer_id], 1.0, BlendMode.NORMAL, crop=self._crops.get(e.layer_id))

    def _cropped_off(self) -> RenderLayer | None:
        """While cropping: the active layer, so its cut-off part can show faintly."""
        if not (self._crop_mode and self._active_editable()):
            return None
        e = self.entry(self._active_id)
        return RenderLayer(e.pixmap, self._quads[e.layer_id], 1.0, BlendMode.NORMAL,
                           crop=self._crops.get(e.layer_id) or FULL_CROP)

    def render_canvas_image(self) -> QImage:
        """The composited canvas at 1 image pixel per canvas pixel."""
        image = QImage(QSize(round(self._canvas.width()), round(self._canvas.height())), QImage.Format_ARGB32_Premultiplied)
        render_canvas(image, QTransform.fromTranslate(-self._canvas.left(), -self._canvas.top()), self._canvas,
                      self._render_layers(), self._grid, self._split_x())
        return image

    def render_thumbnail(self, max_edge: int = 480) -> QImage:
        """The composited canvas scaled so its longer side is `max_edge`."""
        w, h = self._canvas.width(), self._canvas.height()
        scale = max_edge / max(w, h, 1)
        image = QImage(QSize(max(1, round(w * scale)), max(1, round(h * scale))), QImage.Format_ARGB32_Premultiplied)
        transform = QTransform.fromTranslate(-self._canvas.left(), -self._canvas.top()) * QTransform.fromScale(scale, scale)
        render_canvas(image, transform, self._canvas, self._render_layers(), self._grid, self._split_x())
        return image

    def _split_x(self) -> float | None:
        return None if self._split_fraction is None else self._canvas.width() * self._split_fraction

    def drawBackground(self, painter: QPainter, rect: QRectF):
        vp = self.viewport()
        dpr = vp.devicePixelRatioF()
        size = QSize(math.ceil(vp.width() * dpr), math.ceil(vp.height() * dpr))
        if self._buffer is None or self._buffer.size() != size:
            self._buffer = QImage(size, QImage.Format_ARGB32_Premultiplied)
            self._scratch = QImage(size, QImage.Format_ARGB32)
        self._buffer.setDevicePixelRatio(1.0)
        scene_to_device = self.viewportTransform() * QTransform.fromScale(dpr, dpr)
        render_canvas(self._buffer, scene_to_device, self._canvas, self._render_layers(), self._grid,
                      self._split_x(), self._ghost(), smooth=self._drag is None, scratch=self._scratch,
                      cropped_off=self._cropped_off())
        self._buffer.setDevicePixelRatio(dpr)
        painter.save()
        painter.resetTransform()
        painter.drawImage(0, 0, self._buffer)
        painter.restore()

    # -- view fitting ---------------------------------------------------

    def _active_editable(self) -> bool:
        e = self.entry(self._active_id) if self._tool_enabled else None
        return e is not None and e.state.visible

    def refit(self) -> None:
        rect = QRectF(self._canvas)
        if self._active_editable():
            rect = rect.united(QPolygonF([QPointF(*p) for p in self._quads[self._active_id]]).boundingRect())
        margin = max(rect.width(), rect.height()) * 0.08 + 10
        self.fitInView(rect.adjusted(-margin, -margin, margin, margin), Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refit()

    def _scale(self) -> float:
        return self.transform().m11() or 1.0

    # -- transform tool ---------------------------------------------------

    def _drag_layer(self) -> str | None:
        return self._active_id if self._drag else None

    def _hit(self, view_pos) -> tuple | None:
        if not self._active_editable():
            return None
        quad = self._quads[self._active_id]
        vx, vy = view_pos.x(), view_pos.y()

        def near(p) -> bool:
            v = self.mapFromScene(QPointF(*p))
            return math.hypot(v.x() - vx, v.y() - vy) <= HIT_RADIUS_PX

        if self._crop_mode:
            return self._crop_hit(view_pos, near)

        rot, _ = rotation_handle(quad, ROTATE_OFFSET_PX / self._scale())
        if near(rot):
            return ("rotate",)
        for i, p in enumerate(quad):
            if near(p):
                return ("corner", i)
        for i, p in enumerate(edge_midpoints(quad)):
            if near(p):
                return ("edge", i)
        s = self.mapToScene(view_pos)
        if point_in_quad(quad, (s.x(), s.y())):
            return ("move",)
        return None

    def _crop_hit(self, view_pos, near) -> tuple | None:
        layer_id = self._active_id
        crop = self._crops.get(layer_id) or FULL_CROP

        def scene_point(uv):
            q = self._uv_to_scene(layer_id, uv)
            return q.x(), q.y()

        for i, uv in enumerate(crop_corners(crop)):
            if near(scene_point(uv)):
                return ("crop-corner", i)
        for i, uv in enumerate(crop_edge_midpoints(crop)):
            if near(scene_point(uv)):
                return ("crop-edge", i)
        uv = self._scene_to_uv(layer_id, self.mapToScene(view_pos))
        left, top, right, bottom = crop
        if uv is not None and left <= uv[0] <= right and top <= uv[1] <= bottom:
            return ("crop-move",)
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._tool_enabled:
            pos = event.position().toPoint()
            marker = self._marker_at(pos)
            if marker is not None:
                self.markerClicked.emit(marker.swatch_id)
                event.accept()
                return
            if self._pick_enabled:
                s = self.mapToScene(pos)
                self.colorPicked.emit(s.x(), s.y())
                event.accept()
                return
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            handle = self._hit(pos)
            if handle is not None:
                s = self.mapToScene(pos)
                if handle[0].startswith("crop"):
                    start = self._scene_to_uv(self._active_id, s)
                    if start is not None:
                        self._drag = (handle, start, self._crops.get(self._active_id) or FULL_CROP)
                else:
                    self._drag = (handle, (s.x(), s.y()), list(self._quads[self._active_id]))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._pick_enabled:
            self._hover = self.mapToScene(pos)
            self.pickHover.emit((self._hover.x(), self._hover.y()))
            self.viewport().setCursor(Qt.PointingHandCursor if self._marker_at(pos) else Qt.CrossCursor)
            self.viewport().update()
            event.accept()
            return
        if self._drag is not None and self._drag[0][0].startswith("crop"):
            handle, start, start_crop = self._drag
            uv = self._scene_to_uv(self._active_id, self.mapToScene(pos))
            if uv is not None:
                self._crops[self._active_id] = drag_crop(start_crop, handle, start, uv)
                self.viewport().update()
            event.accept()
            return
        if self._drag is not None:
            handle, start, start_quad = self._drag
            s = self.mapToScene(pos)
            new_quad = apply_drag(self._mode, handle, start_quad, start, (s.x(), s.y()))
            if new_quad is not None:
                self._quads[self._active_id] = new_quad
                self.viewport().update()
            event.accept()
            return
        handle = self._hit(pos)
        if handle is None and not self._tool_enabled and self._marker_at(pos):
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self._update_cursor(handle)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag is not None and event.button() == Qt.LeftButton and self._drag[0][0].startswith("crop"):
            self._drag = None
            crop = self._crops.get(self._active_id)
            self.cropCommitted.emit(self._active_id, None if crop in (None, FULL_CROP) else tuple(crop))
            self.viewport().update()
            event.accept()
            return
        if self._drag is not None and event.button() == Qt.LeftButton:
            self._drag = None
            layer_id = self._active_id
            self.quadCommitted.emit(layer_id, list(self._quads[layer_id]))
            if not self.mapToScene(self.viewport().rect()).boundingRect().contains(
                QPolygonF([QPointF(*p) for p in self._quads[layer_id]]).boundingRect()
            ):
                self.refit()
            self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _update_cursor(self, handle) -> None:
        if handle is None:
            self.viewport().unsetCursor()
        elif handle[0] in ("move", "crop-move"):
            self.viewport().setCursor(Qt.SizeAllCursor)
        elif handle[0] == "rotate":
            self.viewport().setCursor(Qt.OpenHandCursor)
        else:
            self.viewport().setCursor(Qt.CrossCursor)

    def leaveEvent(self, event):
        if self._pick_enabled and self._hover is not None:
            self._hover = None
            self.pickHover.emit(None)
            self.viewport().update()
        super().leaveEvent(event)

    def _draw_markers(self, painter: QPainter, scale: float) -> None:
        r = MARKER_RADIUS_PX / scale
        for m in self._markers:
            center = self._marker_point(m)
            if center is None:
                continue
            ring_color = QColor(*m.ring) if m.ring else (ACCENT if m.selected else Qt.white)
            ring = QPen(ring_color, 4 if m.selected else (3 if m.ring else 2))
            ring.setCosmetic(True)
            painter.setPen(ring)
            painter.setBrush(QBrush(QColor(*m.rgb)))
            painter.drawEllipse(center, r, r)
            luminance = 0.299 * m.rgb[0] + 0.587 * m.rgb[1] + 0.114 * m.rgb[2]
            painter.setPen(QPen(Qt.black if luminance > 150 else Qt.white))
            painter.save()  # draw the number at screen size, whatever the zoom
            painter.translate(center)
            painter.scale(1 / scale, 1 / scale)
            f = painter.font()
            f.setPixelSize(11)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(QRectF(-MARKER_RADIUS_PX, -MARKER_RADIUS_PX, 2 * MARKER_RADIUS_PX, 2 * MARKER_RADIUS_PX),
                             Qt.AlignCenter, str(m.number))
            painter.restore()

    def _draw_pick_cursor(self, painter: QPainter, scale: float) -> None:
        if not self._pick_enabled or self._hover is None:
            return
        r = max(self._pick_radius_scene, 4 / scale)
        for color, width in ((Qt.black, 3), (Qt.white, 1.5)):
            pen = QPen(color, width)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(self._hover, r, r)

    def drawForeground(self, painter: QPainter, rect: QRectF):
        scale = self._scale()
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._draw_markers(painter, scale)
        self._draw_pick_cursor(painter, scale)
        if not self._active_editable():
            return
        if self._crop_mode:
            self._draw_crop_frame(painter)
            return
        quad = self._quads[self._active_id]
        scale = self._scale()
        r = HANDLE_RADIUS_PX / scale
        painter.setRenderHint(QPainter.Antialiasing, True)

        pen = QPen(ACCENT, 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(QPolygonF([QPointF(*p) for p in quad]))

        rot, mid = rotation_handle(quad, ROTATE_OFFSET_PX / scale)
        painter.drawLine(QPointF(*mid), QPointF(*rot))

        painter.setBrush(QBrush(Qt.white))
        for p in quad:
            painter.drawRect(QRectF(p[0] - r, p[1] - r, 2 * r, 2 * r))
        for p in edge_midpoints(quad):
            painter.drawEllipse(QPointF(*p), r * 0.85, r * 0.85)
        painter.setBrush(QBrush(ACCENT))
        painter.drawEllipse(QPointF(*rot), r, r)

    def _draw_crop_frame(self, painter: QPainter) -> None:
        """The crop as a white frame with L-shaped corners and edge bars,
        drawn in screen pixels so it reads the same at any zoom."""
        layer_id = self._active_id
        crop = self._crops.get(layer_id) or FULL_CROP
        corners = [self.mapFromScene(self._uv_to_scene(layer_id, uv)) for uv in crop_corners(crop)]
        mids = [self.mapFromScene(self._uv_to_scene(layer_id, uv)) for uv in crop_edge_midpoints(crop)]
        painter.save()
        painter.resetTransform()
        frame = QPolygonF([QPointF(p) for p in corners])
        for color, width in ((QColor(0, 0, 0, 120), 3.0), (Qt.white, 1.5)):
            painter.setPen(QPen(color, width))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(frame)
        pen = QPen(Qt.white, 5)
        pen.setCapStyle(Qt.SquareCap)
        painter.setPen(pen)
        arm = 16.0
        for i, c in enumerate(corners):
            for j in ((i + 1) % 4, (i + 3) % 4):  # a short arm toward each neighbouring corner
                d = QPointF(corners[j]) - QPointF(c)
                length = math.hypot(d.x(), d.y()) or 1.0
                painter.drawLine(QPointF(c), QPointF(c) + d * (min(arm, length / 3) / length))
        for i, m in enumerate(mids):
            a, b = QPointF(corners[i]), QPointF(corners[(i + 1) % 4])
            d = b - a
            length = math.hypot(d.x(), d.y()) or 1.0
            half = d * (min(10.0, length / 6) / length)
            painter.drawLine(QPointF(m) - half, QPointF(m) + half)
        painter.restore()
