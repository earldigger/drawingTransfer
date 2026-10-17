"""The central canvas: shows the composited render and lets the user drag
the active layer around directly (the "Move" transform) with the mouse.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem


class CanvasView(QGraphicsView):
    layerDragDelta = Signal(float, float)  # dx, dy in canvas-pixel space
    dragFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(Qt.darkGray)
        self.setDragMode(QGraphicsView.NoDrag)

        self._dragging = False
        self._last_scene_pos = None
        self._has_content = False

    def set_image(self, pixmap: QPixmap) -> None:
        self._pixmap_item.setPixmap(pixmap)
        rect = QRectF(pixmap.rect())
        self.setSceneRect(rect)
        self._fit()
        self._has_content = True

    def _fit(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._has_content:
            self._dragging = True
            self._last_scene_pos = self.mapToScene(event.position().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            pos = self.mapToScene(event.position().toPoint())
            delta = pos - self._last_scene_pos
            self._last_scene_pos = pos
            if delta.x() != 0 or delta.y() != 0:
                self.layerDragDelta.emit(delta.x(), delta.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self.dragFinished.emit()
        super().mouseReleaseEvent(event)
