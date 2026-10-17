"""Per-layer pixel operations (the Core Image stand-in): perspective
correction, display downscaling, and contrast/invert adjustments.

Images are uint8 RGBA numpy arrays (channel order R, G, B, A). Every
function is pure -- it never modifies its input -- which keeps layers
nondestructive: the raw imported photo is always kept as-is and these
run on demand to produce what is displayed.
"""

from __future__ import annotations

import math

import numpy as np
import cv2

from .models import PerspectiveCorners

MAX_DISPLAY_EDGE = 2400
CONTRAST_RANGE = 4.0  # contrast=+1 multiplies spread around mid-gray by 4, -1 divides by 4


def capped_size(w: float, h: float, max_edge: int = MAX_DISPLAY_EDGE) -> tuple[int, int]:
    s = min(1.0, max_edge / max(w, h))
    return max(1, round(w * s)), max(1, round(h * s))


def corrected_size(corners: PerspectiveCorners) -> tuple[float, float]:
    """Width/height of the photographed rectangle estimated from its
    corners (longest opposite edges). Approximate -- true proportions would
    need the camera's lens data -- but close for photos taken near head-on.
    """
    tl, tr, br, bl = corners.as_list()
    width = max(math.dist(tl, tr), math.dist(bl, br))
    height = max(math.dist(tl, bl), math.dist(tr, br))
    return max(width, 1.0), max(height, 1.0)


def perspective_correct(image: np.ndarray, corners: PerspectiveCorners, output_size: tuple[int, int]) -> np.ndarray:
    """Warp the quadrilateral at `corners` onto a `output_size` (w, h) rectangle."""
    w, h = output_size
    src = np.array(corners.as_list(), dtype=np.float32)
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(
        image, matrix, (w, h),
        flags=cv2.INTER_AREA if w * h < image.shape[0] * image.shape[1] else cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0),
    )


def downscale_to_max(image: np.ndarray, max_edge: int = MAX_DISPLAY_EDGE) -> np.ndarray:
    h, w = image.shape[:2]
    new_w, new_h = capped_size(w, h, max_edge)
    if (new_w, new_h) == (w, h):
        return image
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def adjustment_lut(contrast: float, invert: bool) -> np.ndarray:
    factor = CONTRAST_RANGE ** float(np.clip(contrast, -1.0, 1.0))
    values = (np.arange(256, dtype=np.float32) - 127.5) * factor + 127.5
    lut = np.clip(np.round(values), 0, 255).astype(np.uint8)
    if invert:
        lut = 255 - lut
    return lut


def adjust(image: np.ndarray, contrast: float = 0.0, invert: bool = False) -> np.ndarray:
    """Contrast around mid-gray and/or RGB inversion; alpha is untouched."""
    if contrast == 0.0 and not invert:
        return image
    out = image.copy()
    out[..., :3] = cv2.LUT(np.ascontiguousarray(image[..., :3]), adjustment_lut(contrast, invert))
    return out
