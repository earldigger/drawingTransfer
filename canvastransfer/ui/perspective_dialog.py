"""Four-point perspective correction dialog: drag a corner onto each corner
of the photographed drawing/canvas; Apply warps that quad to a rectangle.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QBrush, QPen, QColor, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsPolygonItem,
    QPushButton,
    QLabel,
)

from ..models import PerspectiveCorners
from .image_qt import rgba_float_to_qpixmap

HANDLE_COLOR = QColor(255, 60, 60)
LINE_COLOR = QColor(255, 60, 60, 200)
CORNER_ORDER = ["top_left", "top_right", "bottom_right", "bottom_left"]


class _CornerHandle(QGraphicsEllipseItem):
    def __init__(self, radius: float, on_move):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self._on_move = on_move
        self.setBrush(QBrush(HANDLE_COLOR))
        self.setPen(QPen(Qt.white, max(1.0, radius / 6)))
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.ItemSendsGeometryChanges, True)
        self.setZValue(10)

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsEllipseItem.ItemPositionHasChanged:
            self._on_move()
        return result


class PerspectiveDialog(QDialog):
    def __init__(self, image_float_rgba: np.ndarray, initial_corners: PerspectiveCorners | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Perspective Correction")
        self.resize(760, 640)

        self._image_shape = image_float_rgba.shape[:2]  # h, w
        self._default_corners = PerspectiveCorners.default_for_image(
            self._image_shape[1], self._image_shape[0]
        )
        self._result_corners: PerspectiveCorners | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Drag each red handle onto a corner of the drawing or canvas."))

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(self.view.renderHints() | self.view.renderHints())
        layout.addWidget(self.view)

        pixmap = rgba_float_to_qpixmap(image_float_rgba)
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))

        radius = max(6.0, min(self._image_shape[0], self._image_shape[1]) * 0.015)
        self._handles: list[_CornerHandle] = []
        self.polygon_item = QGraphicsPolygonItem()
        self.polygon_item.setPen(QPen(LINE_COLOR, max(2.0, radius / 3)))
        self.polygon_item.setBrush(QBrush(QColor(255, 60, 60, 40)))
        self.scene.addItem(self.polygon_item)

        corners = initial_corners or self._default_corners
        for point in corners.as_list():
            handle = _CornerHandle(radius, self._update_polygon)
            handle.setPos(QPointF(point[0], point[1]))
            self.scene.addItem(handle)
            self._handles.append(handle)
        self._update_polygon()

        buttons = QHBoxLayout()
        reset_btn = QPushButton("Reset")
        cancel_btn = QPushButton("Cancel")
        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        buttons.addWidget(reset_btn)
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(apply_btn)
        layout.addLayout(buttons)

        reset_btn.clicked.connect(self._reset)
        cancel_btn.clicked.connect(self.reject)
        apply_btn.clicked.connect(self._apply)

    def showEvent(self, event):
        super().showEvent(event)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def _update_polygon(self):
        self.polygon_item.setPolygon(QPolygonF([h.pos() for h in self._handles]))

    def _reset(self):
        for handle, point in zip(self._handles, self._default_corners.as_list()):
            handle.setPos(QPointF(point[0], point[1]))
        self._update_polygon()

    def _apply(self):
        positions = {name: (h.pos().x(), h.pos().y()) for name, h in zip(CORNER_ORDER, self._handles)}
        self._result_corners = PerspectiveCorners(**positions)
        self.accept()

    def result_corners(self) -> PerspectiveCorners | None:
        return self._result_corners
