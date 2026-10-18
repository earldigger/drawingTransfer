"""Per-layer pixel operations (the Core Image stand-in): perspective
correction, display downscaling, and value/color adjustments.

Images are uint8 RGBA numpy arrays (channel order R, G, B, A). Every
function is pure -- it never modifies its input -- which keeps layers
nondestructive: the raw imported photo is always kept as-is and these
run on demand to produce what is displayed.
"""

from __future__ import annotations

import math

import numpy as np
import cv2

from .models import Adjustments, PerspectiveCorners

MAX_DISPLAY_EDGE = 2400
COLOR_SHIFT_STRENGTH = 0.3  # how far temperature/tint at +-100 move the channels


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


def levels_curve(black: int, gamma: float, white: int, invert: bool = False) -> np.ndarray:
    """0..1 output for each 0..255 input: optional invert, then Photoshop-
    style input levels (dark point -> black, light point -> white, midtones
    bent by gamma)."""
    x = np.arange(256, dtype=np.float32)
    if invert:
        x = 255.0 - x
    span = max(float(white - black), 1.0)
    t = np.clip((x - black) / span, 0.0, 1.0)
    return t ** (1.0 / max(gamma, 1e-3))


def color_gains(temperature: float, tint: float) -> tuple[float, float, float]:
    """R, G, B multipliers. Temperature runs blue <-> yellow (yellow = red +
    green), tint runs green <-> magenta (magenta = red + blue), matching
    the two axes of Photoshop's sliders."""
    t = COLOR_SHIFT_STRENGTH * float(np.clip(temperature, -1.0, 1.0))
    m = COLOR_SHIFT_STRENGTH * float(np.clip(tint, -1.0, 1.0))
    return (
        (1.0 + t / 2) * (1.0 + m / 2),
        (1.0 + t / 2) * (1.0 - m),
        (1.0 - t) * (1.0 + m / 2),
    )


def tone_lut(adj: Adjustments) -> np.ndarray:
    """RGBA lookup table (256, 1, 4) for invert + levels + temperature/tint.
    Alpha maps to itself; doing all four channels in one LUT call avoids
    slow per-channel slicing of large images."""
    curve = levels_curve(adj.black, adj.gamma, adj.white, adj.invert) * 255.0
    gains = color_gains(adj.temperature, adj.tint)
    channels = [np.clip(np.round(curve * g), 0, 255) for g in gains] + [np.arange(256)]
    return np.stack(channels, axis=-1).astype(np.uint8).reshape(256, 1, 4)


def _tone_is_identity(adj: Adjustments) -> bool:
    return (not adj.invert and adj.black == 0 and adj.white == 255 and adj.gamma == 1.0
            and adj.temperature == 0.0 and adj.tint == 0.0)


def _saturate(rgb: np.ndarray, vibrance: float, saturation: float) -> np.ndarray:
    """Push each pixel away from (or toward) its own gray. Vibrance scales
    the push by how muted the pixel already is, so strong colors hold."""
    sat = cv2.extractChannel(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV), 1)
    muted = 1.0 - np.arange(256, dtype=np.float32) / 255.0
    factor_lut = ((1.0 + saturation) * (1.0 + vibrance * muted)).astype(np.float32)
    factor = cv2.LUT(sat, factor_lut)
    gray = cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    # gray + (color - gray) * factor, as one fast weighted blend
    return cv2.blendLinear(rgb, gray, factor, 1.0 - factor)


def apply_adjustments(image: np.ndarray, adj: Adjustments) -> np.ndarray:
    """Returns `image` itself when nothing is adjusted; alpha is untouched."""
    if adj == Adjustments():
        return image
    out = image if _tone_is_identity(adj) else cv2.LUT(image, tone_lut(adj))
    if adj.vibrance != 0.0 or adj.saturation != 0.0:
        rgb = _saturate(
            cv2.cvtColor(out, cv2.COLOR_RGBA2RGB),
            float(np.clip(adj.vibrance, -1, 1)),
            float(np.clip(adj.saturation, -1, 1)),
        )
        out_rgba = cv2.cvtColor(rgb, cv2.COLOR_RGB2RGBA)
        cv2.mixChannels([image], [out_rgba], [3, 3])  # restore original alpha
        out = out_rgba
    return out
