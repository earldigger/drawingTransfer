"""Conversion helpers between our float32 RGBA numpy arrays and Qt images."""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap

from ..compositing import to_uint8_rgba


def rgba_float_to_qpixmap(image_float_rgba: np.ndarray) -> QPixmap:
    rgba_uint8 = np.ascontiguousarray(to_uint8_rgba(image_float_rgba))
    h, w = rgba_uint8.shape[:2]
    qimage = QImage(rgba_uint8.data, w, h, rgba_uint8.strides[0], QImage.Format_RGBA8888)
    # QImage does not copy the buffer by default; copy() detaches it from
    # the numpy array before that array can be garbage collected.
    return QPixmap.fromImage(qimage.copy())
