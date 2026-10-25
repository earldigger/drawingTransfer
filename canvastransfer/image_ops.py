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

from .models import DEFAULT_LOOK, Adjustments, BlendMode, Layer, LayerKind, PerspectiveCorners

MAX_DISPLAY_EDGE = 2400


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


AUTO_LEVELS_CLIP = 0.5  # percent of pixels allowed to clip at each end
AUTO_LEVELS_MIN_SPAN = 32  # never stretch a nearly flat image into noise


def auto_levels(image: np.ndarray) -> tuple[int, int]:
    """Dark and light points (0..255) that stretch the image's luminance to
    the full range, ignoring the darkest and lightest AUTO_LEVELS_CLIP %
    (specks, glare). For a photographed drawing this turns gray paper white
    and the lines dark. Transparent pixels are ignored."""
    rgb = image[..., :3].astype(np.float32)
    luma = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    if image.shape[-1] == 4:
        luma = luma[image[..., 3] > 0]
    if luma.size == 0:
        return 0, 255
    black, white = (int(round(v)) for v in np.percentile(luma, [AUTO_LEVELS_CLIP, 100 - AUTO_LEVELS_CLIP]))
    if white - black < AUTO_LEVELS_MIN_SPAN:
        return 0, 255
    return black, white


def default_look(kind: LayerKind, image: np.ndarray) -> tuple[float, BlendMode, Adjustments]:
    """Opacity, blend mode and adjustments a new layer of this kind starts with."""
    opacity, blend, levels = DEFAULT_LOOK[kind]
    black, white = auto_levels(image) if levels else (0, 255)
    return opacity, blend, Adjustments(black=black, white=white)


def has_default_look(layer: Layer, image: np.ndarray) -> bool:
    """True when the layer still looks exactly as its kind starts, i.e. the
    user hasn't touched opacity, blend or adjustments."""
    opacity, blend, adjustments = default_look(layer.kind, image)
    return (layer.opacity, layer.blend_mode, layer.adjustments) == (opacity, blend, adjustments)


def _rgba_lut(rgb_lut: np.ndarray) -> np.ndarray:
    """(256, 1, 4) LUT applying `rgb_lut` (256,) to R, G, B and leaving alpha.
    One 4-channel LUT call avoids slow per-channel slicing of large images."""
    rgb_lut = np.clip(np.round(rgb_lut), 0, 255)
    return np.stack([rgb_lut, rgb_lut, rgb_lut, np.arange(256)], axis=-1).astype(np.uint8).reshape(256, 1, 4)


def levels_lut(adj: Adjustments) -> np.ndarray:
    return _rgba_lut(levels_curve(adj.black, adj.gamma, adj.white, adj.invert) * 255.0)


def lightness_curve(lightness: int) -> np.ndarray:
    """Photoshop Hue/Saturation lightness: blend toward white (+) or black (-)."""
    x = np.arange(256, dtype=np.float32)
    v = float(np.clip(lightness, -100, 100)) / 100.0
    return x + (255.0 - x) * v if v >= 0 else x * (1.0 + v)


def _levels_is_identity(adj: Adjustments) -> bool:
    return not adj.invert and adj.black == 0 and adj.white == 255 and adj.gamma == 1.0


def _hue_sat_is_identity(adj: Adjustments) -> bool:
    return not adj.colorize and adj.hue == 0 and adj.saturation == 0


def _hue_saturation(rgb: np.ndarray, adj: Adjustments) -> np.ndarray:
    """Hue shift + saturation in HLS space, or Colorize. OpenCV's 8-bit HLS
    stores hue as 0..179 (2 degrees per step), lightness and saturation as
    0..255."""
    if adj.colorize:
        # Keep each pixel's brightness, replace its color with one tint.
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        hue = np.full_like(gray, round((adj.colorize_hue % 360) / 2) % 180)
        sat = np.full_like(gray, round(255 * np.clip(adj.colorize_saturation, 0, 100) / 100))
        return cv2.cvtColor(cv2.merge([hue, gray, sat]), cv2.COLOR_HLS2RGB)

    i = np.arange(256)
    shift = round(np.clip(adj.hue, -180, 180) / 2)
    # Hue 180 can occur for colors just short of 360 degrees; it means red, so wrap it too.
    hue_lut = np.where(i <= 180, (i + shift) % 180, i)
    sat_lut = np.clip(np.round(i * (1.0 + np.clip(adj.saturation, -100, 100) / 100.0)), 0, 255)
    lut = np.stack([hue_lut, i, sat_lut], axis=-1).astype(np.uint8).reshape(256, 1, 3)
    return cv2.cvtColor(cv2.LUT(cv2.cvtColor(rgb, cv2.COLOR_RGB2HLS), lut), cv2.COLOR_HLS2RGB)


def apply_adjustments(image: np.ndarray, adj: Adjustments) -> np.ndarray:
    """Returns `image` itself when nothing is adjusted; alpha is untouched."""
    if adj == Adjustments():
        return image
    out = image if _levels_is_identity(adj) else cv2.LUT(image, levels_lut(adj))
    if not _hue_sat_is_identity(adj):
        rgb = _hue_saturation(cv2.cvtColor(out, cv2.COLOR_RGBA2RGB), adj)
        out_rgba = cv2.cvtColor(rgb, cv2.COLOR_RGB2RGBA)
        cv2.mixChannels([image], [out_rgba], [3, 3])  # restore original alpha
        out = out_rgba
    if adj.lightness != 0:
        out = cv2.LUT(out, _rgba_lut(lightness_curve(adj.lightness)))
    return out
