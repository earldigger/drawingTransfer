"""The canvas: shows every layer live in a Qt scene and hosts the
Fresco-style transform tool (8 handles + rotation handle on the active
layer, drag inside to move).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from ..compare import DisplayState
from ..geometry import (
    Quad,
    TransformMode,
    apply_drag,
    edge_midpoints,
    point_in_quad,
    rotation_handle,
)
from ..models import GridSettings
from .scene_items import GridItem, LayerItem

HANDLE_RADIUS_PX = 6
HIT_RADIUS_PX = 12
ROTATE_OFFSET_PX = 34
ACCENT = QColor(30, 144, 255)
GHOST_OPACITY = 0.3


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
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor(64, 64, 64))
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)

        self._canvas = QRectF(0, 0, 1, 1)
        self._bg = QGraphicsRectItem()
        self._bg.setBrush(QBrush(Qt.white))
        self._bg.setPen(QPen(Qt.NoPen))
        self._bg.setZValue(-1)
        self._scene.addItem(self._bg)

        # Off-canvas parts of the active layer show faintly while
        # transforming: the ghost sits under the opaque canvas, so only the
        # part outside the canvas is visible.
        self._ghost = LayerItem()
        self._ghost.setZValue(-2)
        self._ghost.setOpacity(GHOST_OPACITY)
        self._ghost.hide()
        self._scene.addItem(self._ghost)

        self._root = QGraphicsRectItem()
        self._root.setPen(QPen(Qt.NoPen))
        self._root.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True)
        self._scene.addItem(self._root)

        self._grid = GridItem(self._root)
        self._grid.setZValue(1_000_000)
        self._grid.hide()

        self._split_line = QGraphicsLineItem()
        pen = QPen(Qt.white, 2)
        pen.setCosmetic(True)
        self._split_line.setPen(pen)
        self._split_line.setZValue(10)
        self._split_line.hide()
        self._scene.addItem(self._split_line)

        self._items: dict[str, LayerItem] = {}
        self._quads: dict[str, Quad] = {}
        self._visible: dict[str, bool] = {}
        self._active_id: str | None = None
        self._tool_enabled = False
        self._mode = TransformMode.UNIFORM
        self._drag: tuple | None = None  # (handle, start point, start quad)

    # -- configuration ------------------------------------------------

    def set_canvas_size(self, width: int, height: int) -> None:
        self._canvas = QRectF(0, 0, width, height)
        self._bg.setRect(self._canvas)
        self._root.setRect(self._canvas)
        self._grid.set_rect(self._canvas)
        self._scene.setSceneRect(self._canvas.adjusted(-20000, -20000, 20000, 20000))
        self.refit()

    def set_grid(self, grid: GridSettings) -> None:
        self._grid.set_grid(grid)

    def show_layers(self, entries: list[LayerEntry], split_fraction: float | None) -> None:
        """Display layers bottom-to-top as described by `entries`."""
        wanted = {e.layer_id for e in entries}
        for layer_id in list(self._items):
            if layer_id not in wanted:
                self._scene.removeItem(self._items.pop(layer_id))
                self._quads.pop(layer_id, None)
                self._visible.pop(layer_id, None)

        split_x = None if split_fraction is None else self._canvas.width() * split_fraction
        for z, entry in enumerate(entries):
            item = self._items.get(entry.layer_id)
            if item is None:
                item = LayerItem(self._root)
                self._items[entry.layer_id] = item
            if item.pixmap().cacheKey() != entry.pixmap.cacheKey():
                item.setPixmap(entry.pixmap)
            item.setZValue(z)
            if self._drag is None or self._drag_layer() != entry.layer_id:
                self._quads[entry.layer_id] = list(entry.quad)
                item.set_quad(entry.quad)
            state = entry.state
            item.setVisible(state.visible)
            item.setOpacity(state.opacity)
            item.multiply = state.multiply
            item.scene_clip = self._clip_rect(state.clip, split_x)
            item.update()
            self._visible[entry.layer_id] = state.visible

        if split_x is None:
            self._split_line.hide()
        else:
            self._split_line.setLine(split_x, 0, split_x, self._canvas.height())
            self._split_line.show()
        self._sync_ghost()
        self.viewport().update()

    def _clip_rect(self, side: str | None, split_x: float | None) -> QRectF | None:
        if side is None or split_x is None:
            return None
        c = self._canvas
        if side == "left":
            return QRectF(c.left(), c.top(), split_x - c.left(), c.height())
        return QRectF(split_x, c.top(), c.right() - split_x, c.height())

    def set_active_layer(self, layer_id: str | None) -> None:
        if layer_id != self._active_id:
            self._active_id = layer_id
            self._sync_ghost()
            if self._tool_enabled:
                self.refit()
            self.viewport().update()

    def set_tool(self, enabled: bool, mode: TransformMode) -> None:
        turned_on = enabled and not self._tool_enabled
        self._tool_enabled = enabled
        self._mode = mode
        self._sync_ghost()
        if turned_on:
            self.refit()
        self.viewport().update()

    def quad(self, layer_id: str) -> Quad | None:
        return self._quads.get(layer_id)

    # -- view fitting ---------------------------------------------------

    def _active_editable(self) -> bool:
        return (
            self._tool_enabled
            and self._active_id in self._items
            and self._visible.get(self._active_id, False)
        )

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

    def _sync_ghost(self) -> None:
        item = self._items.get(self._active_id)
        if not self._active_editable() or item is None:
            self._ghost.hide()
            return
        if self._ghost.pixmap().cacheKey() != item.pixmap().cacheKey():
            self._ghost.setPixmap(item.pixmap())
        self._ghost.set_quad(self._quads[self._active_id])
        self._ghost.show()

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

    def _set_fast(self, fast: bool) -> None:
        for item in self._items.values():
            item.fast = fast
        self._ghost.fast = fast

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            handle = self._hit(pos)
            if handle is not None:
                s = self.mapToScene(pos)
                self._drag = (handle, (s.x(), s.y()), list(self._quads[self._active_id]))
                self._set_fast(True)
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
                self._items[self._active_id].set_quad(new_quad)
                self._ghost.set_quad(new_quad)
                self.viewport().update()
            event.accept()
            return
        self._update_cursor(self._hit(pos))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag is not None and event.button() == Qt.LeftButton:
            self._drag = None
            self._set_fast(False)
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

        outline = QPen(ACCENT, 1.5)
        outline.setCosmetic(True)
        painter.setPen(outline)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(QPolygonF([QPointF(*p) for p in quad]))

        rot, mid = rotation_handle(quad, ROTATE_OFFSET_PX / scale)
        painter.drawLine(QPointF(*mid), QPointF(*rot))

        handle_pen = QPen(ACCENT, 1.5)
        handle_pen.setCosmetic(True)
        painter.setPen(handle_pen)
        painter.setBrush(QBrush(Qt.white))
        for p in quad:
            painter.drawRect(QRectF(p[0] - r, p[1] - r, 2 * r, 2 * r))
        for p in edge_midpoints(quad):
            painter.drawEllipse(QPointF(*p), r * 0.85, r * 0.85)
        painter.setBrush(QBrush(ACCENT))
        painter.drawEllipse(QPointF(*rot), r, r)
