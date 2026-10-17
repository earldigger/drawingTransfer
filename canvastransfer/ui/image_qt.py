"""Conversion from uint8 RGBA numpy arrays to Qt images."""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap


def rgba_to_qpixmap(image_rgba: np.ndarray) -> QPixmap:
    data = np.ascontiguousarray(image_rgba)
    h, w = data.shape[:2]
    qimage = QImage(data.data, w, h, data.strides[0], QImage.Format_RGBA8888)
    # QImage wraps the numpy buffer without copying; copy() detaches it
    # before the array can be garbage collected.
    return QPixmap.fromImage(qimage.copy())
