"""Four-point perspective correction dialog: drag a corner onto each corner
of the photographed drawing/canvas; Apply warps that quad to a rectangle.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsEllipseItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from ..models import PerspectiveCorners
from .image_qt import rgba_to_qpixmap

HANDLE_COLOR = QColor(255, 60, 60)
CORNER_ORDER = ["top_left", "top_right", "bottom_right", "bottom_left"]


class _CornerHandle(QGraphicsEllipseItem):
    def __init__(self, radius: float, bounds: QRectF, on_move):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self._bounds = bounds
        self._on_move = on_move
        self.setBrush(QBrush(HANDLE_COLOR))
        pen = QPen(Qt.white, 2)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CrossCursor)
        self.setZValue(10)

    def itemChange(self, change, value):
        if change == QGraphicsEllipseItem.ItemPositionChange:
            b = self._bounds
            return QPointF(min(max(value.x(), b.left()), b.right()), min(max(value.y(), b.top()), b.bottom()))
        result = super().itemChange(change, value)
        if change == QGraphicsEllipseItem.ItemPositionHasChanged:
            self._on_move()
        return result


class PerspectiveDialog(QDialog):
    def __init__(
        self,
        image_rgba: np.ndarray,
        initial_corners: PerspectiveCorners | None,
        fill_canvas: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Perspective Correction")
        self.resize(820, 700)

        h, w = image_rgba.shape[:2]
        self._default_corners = PerspectiveCorners.default_for_image(w, h)
        self._result_corners: PerspectiveCorners | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Drag each red handle onto a corner of the drawing or canvas."))

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.view.setBackgroundBrush(QColor(64, 64, 64))
        layout.addWidget(self.view)

        bounds = QRectF(0, 0, w, h)
        self.scene.addPixmap(rgba_to_qpixmap(image_rgba))
        self.scene.setSceneRect(bounds)

        radius = max(6.0, min(w, h) * 0.012)
        self.polygon_item = QGraphicsPolygonItem()
        outline = QPen(QColor(255, 60, 60, 220), 2)
        outline.setCosmetic(True)
        self.polygon_item.setPen(outline)
        self.polygon_item.setBrush(QBrush(QColor(255, 60, 60, 40)))
        self.scene.addItem(self.polygon_item)

        self._handles: list[_CornerHandle] = []
        for x, y in (initial_corners or self._default_corners).as_list():
            handle = _CornerHandle(radius, bounds, self._update_polygon)
            handle.setPos(QPointF(x, y))
            self.scene.addItem(handle)
            self._handles.append(handle)
        self._update_polygon()

        self.keep_radio = QRadioButton("Keep the photo's proportions (drawing or reference)")
        self.fill_radio = QRadioButton("Stretch to fill the canvas (photo of the canvas itself)")
        (self.fill_radio if fill_canvas else self.keep_radio).setChecked(True)
        layout.addWidget(self.keep_radio)
        layout.addWidget(self.fill_radio)

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def _update_polygon(self):
        self.polygon_item.setPolygon(QPolygonF([h.pos() for h in self._handles]))

    def _reset(self):
        for handle, (x, y) in zip(self._handles, self._default_corners.as_list()):
            handle.setPos(QPointF(x, y))
        self._update_polygon()

    def _apply(self):
        positions = {name: (h.pos().x(), h.pos().y()) for name, h in zip(CORNER_ORDER, self._handles)}
        self._result_corners = PerspectiveCorners(**positions)
        self.accept()

    def result_corners(self) -> PerspectiveCorners | None:
        return self._result_corners

    def result_fill_canvas(self) -> bool:
        return self.fill_radio.isChecked()
