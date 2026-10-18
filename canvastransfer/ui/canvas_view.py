"""The canvas: composites every layer live (via canvas_render) and hosts
the Fresco-style transform tool (8 handles + rotation handle on the active
layer, drag inside to move).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap, QPolygonF, QTransform
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from ..compare import DisplayState
from ..geometry import Quad, TransformMode, apply_drag, edge_midpoints, point_in_quad, rotation_handle
from ..models import BlendMode, GridSettings
from .canvas_render import RenderLayer, render_canvas

HANDLE_RADIUS_PX = 6
HIT_RADIUS_PX = 12
ROTATE_OFFSET_PX = 34
ACCENT = QColor(30, 144, 255)


@dataclass
class LayerEntry:
    layer_id: str
    pixmap: QPixmap
    quad: Quad
    state: DisplayState


class CanvasView(QGraphicsView):
    quadCommitted = Signal(str, object)  # layer_id, quad in canvas px

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
        self._grid: GridSettings | None = None
        self._split_fraction: float | None = None
        self._active_id: str | None = None
        self._tool_enabled = False
        self._mode = TransformMode.UNIFORM
        self._drag: tuple | None = None  # (handle, start point, start quad)
        self._buffer: QImage | None = None
        self._scratch: QImage | None = None

    # -- configuration ------------------------------------------------

    def set_canvas_size(self, width: int, height: int) -> None:
        self._canvas = QRectF(0, 0, width, height)
        self.scene().setSceneRect(self._canvas.adjusted(-20000, -20000, 20000, 20000))
        self.refit()

    def set_grid(self, grid: GridSettings) -> None:
        self._grid = grid
        self.viewport().update()

    def show_layers(self, entries: list[LayerEntry], split_fraction: float | None) -> None:
        """Display layers bottom-to-top as described by `entries`."""
        dragging = self._drag_layer()
        self._entries = list(entries)
        for entry in entries:
            if entry.layer_id != dragging:
                self._quads[entry.layer_id] = list(entry.quad)
        wanted = {e.layer_id for e in entries}
        self._quads = {k: v for k, v in self._quads.items() if k in wanted}
        self._split_fraction = split_fraction
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

    def quad(self, layer_id: str) -> Quad | None:
        return self._quads.get(layer_id)

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
            layers.append(RenderLayer(e.pixmap, self._quads[e.layer_id], e.state.opacity, e.state.blend, clip))
        return layers

    def _ghost(self) -> RenderLayer | None:
        if not self._active_editable():
            return None
        e = self.entry(self._active_id)
        return RenderLayer(e.pixmap, self._quads[e.layer_id], 1.0, BlendMode.NORMAL)

    def render_canvas_image(self) -> QImage:
        """The composited canvas at 1 image pixel per canvas pixel."""
        image = QImage(QSize(round(self._canvas.width()), round(self._canvas.height())), QImage.Format_ARGB32_Premultiplied)
        render_canvas(image, QTransform.fromTranslate(-self._canvas.left(), -self._canvas.top()), self._canvas,
                      self._render_layers(), self._grid, self._split_x())
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
                      self._split_x(), self._ghost(), smooth=self._drag is None, scratch=self._scratch)
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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            handle = self._hit(pos)
            if handle is not None:
                s = self.mapToScene(pos)
                self._drag = (handle, (s.x(), s.y()), list(self._quads[self._active_id]))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._drag is not None:
            handle, start, start_quad = self._drag
            s = self.mapToScene(pos)
            new_quad = apply_drag(self._mode, handle, start_quad, start, (s.x(), s.y()))
            if new_quad is not None:
                self._quads[self._active_id] = new_quad
                self.viewport().update()
            event.accept()
            return
        self._update_cursor(self._hit(pos))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
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
        elif handle[0] == "move":
            self.viewport().setCursor(Qt.SizeAllCursor)
        elif handle[0] == "rotate":
            self.viewport().setCursor(Qt.OpenHandCursor)
        else:
            self.viewport().setCursor(Qt.CrossCursor)

    def drawForeground(self, painter: QPainter, rect: QRectF):
        if not self._active_editable():
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
