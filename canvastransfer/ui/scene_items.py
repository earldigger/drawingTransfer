"""Graphics items that make up the canvas scene."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem

from ..geometry import Quad
from ..models import GridSettings


class LayerItem(QGraphicsPixmapItem):
    """A layer's pixmap, mapped onto its quad by a projective transform.
    Blending happens here, as the item paints over the layers below it,
    the same way a CIFilter chain composites bottom to top.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.multiply = False
        self.scene_clip: QRectF | None = None
        self.fast = False  # nearest-neighbour while dragging, smooth otherwise
        self.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)
        self.setAcceptedMouseButtons(Qt.NoButton)

    def set_quad(self, quad: Quad) -> bool:
        pm = self.pixmap()
        if pm.isNull():
            return False
        w, h = pm.width(), pm.height()
        source = QPolygonF([QPointF(0, 0), QPointF(w, 0), QPointF(w, h), QPointF(0, h)])
        target = QPolygonF([QPointF(x, y) for x, y in quad])
        transform = QTransform()
        if not QTransform.quadToQuad(source, target, transform):
            return False
        self.setTransform(transform)
        return True

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()
        if self.multiply:
            painter.setCompositionMode(QPainter.CompositionMode_Multiply)
        if self.scene_clip is not None:
            path = QPainterPath()
            path.addPolygon(self.mapFromScene(self.scene_clip))
            painter.setClipPath(path, Qt.IntersectClip)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, not self.fast)
        painter.drawPixmap(0, 0, self.pixmap())
        painter.restore()


class GridItem(QGraphicsItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rect = QRectF()
        self._grid = GridSettings()
        self.setAcceptedMouseButtons(Qt.NoButton)

    def set_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = rect

    def set_grid(self, grid: GridSettings) -> None:
        self._grid = grid
        self.setVisible(grid.enabled)
        self.update()

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None):
        g = self._grid
        if g.rows < 1 or g.columns < 1:
            return
        r, gr, b = g.color
        pen = QPen(QColor(r, gr, b, round(255 * g.opacity)), g.thickness_px)
        pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)
        rect = self._rect
        for i in range(1, g.columns):
            x = rect.left() + rect.width() * i / g.columns
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for i in range(1, g.rows):
            y = rect.top() + rect.height() * i / g.rows
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
