"""Color study math: sampling, CIELAB / Munsell readouts, warm-cool,
complements, tints/shades/tones, and similar-color highlighting.

Whole images use OpenCV (fast); single colors use colour-science (more
exact, and the only source of Munsell). The two agree to within ~0.1 L*a*b*.
Mixing for tints/shades/tones uses Mixbox (CC BY-NC 4.0: personal use only),
which behaves like pigment (yellow + black goes olive, not dull yellow).
"""

from __future__ import annotations

import math
import warnings
from functools import lru_cache

import cv2
import mixbox
import numpy as np

RGB = tuple[int, int, int]

HIGHLIGHT_RGB = (255, 236, 0)
MIX_STEPS = (0.0, 0.2, 0.4, 0.6, 0.8, 0.94)  # share of the added white/black/gray
WHITE, BLACK, GRAY = (255, 255, 255), (0, 0, 0), (128, 128, 128)


def _colour():
    """colour-science is slow to import, so load it on first use."""
    import colour

    warnings.filterwarnings("ignore", module="colour")
    return colour


def warm_up() -> None:
    """Import colour-science and prime the Munsell code ahead of the first
    pick (run once just after the window opens; the first use otherwise
    stalls the first pick for about a second)."""
    munsell((128, 128, 127))


def _illuminants():
    return _colour().CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]


def _xyz_d65(rgb: RGB) -> np.ndarray:
    return _colour().sRGB_to_XYZ(np.asarray(rgb, dtype=float) / 255.0)


def _adapt(xyz: np.ndarray, src: str, dst: str) -> np.ndarray:
    c, ill = _colour(), _illuminants()
    return c.chromatic_adaptation(xyz, c.xy_to_XYZ(ill[src]), c.xy_to_XYZ(ill[dst]),
                                  method="Von Kries", transform="Bradford")


def hex_code(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def lab_d65(rgb: RGB) -> np.ndarray:
    return _colour().XYZ_to_Lab(_xyz_d65(rgb), _illuminants()["D65"])


def lab_d50(rgb: RGB) -> np.ndarray:
    """CIELAB under D50, the convention artistpigments.org lists paints in."""
    return _colour().XYZ_to_Lab(_adapt(_xyz_d65(rgb), "D65", "D50"), _illuminants()["D50"])


@lru_cache(maxsize=512)
def munsell(rgb: RGB) -> tuple[str | None, float]:
    """(Munsell notation or None, Munsell value 0..10). Munsell is defined
    under illuminant C. Value always works (ASTM D1535); the full notation
    fails for colors outside the renotation data, e.g. deep saturated blues."""
    c = _colour()
    xyy = c.XYZ_to_xyY(_adapt(_xyz_d65(rgb), "D65", "C"))
    value = float(c.munsell_value(xyy[2] * 100, method="ASTM D1535"))
    try:
        notation = c.xyY_to_munsell_colour(xyy)
    except (ValueError, AssertionError, RuntimeError):
        notation = None
    return notation, value


def temperature(rgb: RGB) -> tuple[float, str]:
    """Warm (+1) to cool (-1). There is no standard definition; this is a
    rule of thumb: warmest around orange, coolest around cyan-blue, and
    muted colors pulled toward neutral."""
    _, a, b = lab_d65(rgb)
    chroma = math.hypot(a, b)
    hue = math.degrees(math.atan2(b, a))
    score = math.cos(math.radians(hue - 55.0)) * min(1.0, chroma / 40.0)
    for limit, label in ((-0.6, "Very Cool"), (-0.2, "Cool"), (0.2, "Neutral"), (0.6, "Warm")):
        if score < limit:
            return score, label
    return score, "Very Warm"


def complement(rgb: RGB) -> RGB:
    """Opposite hue in CIELAB at the same lightness, with chroma reduced
    only as far as needed to fit on screen."""
    c = _colour()
    L, a, b = lab_d65(rgb)
    d65 = _illuminants()["D65"]

    def srgb(scale: float) -> np.ndarray:
        return c.XYZ_to_sRGB(c.Lab_to_XYZ([L, -a * scale, -b * scale], d65))

    def fits(v: np.ndarray) -> bool:
        return bool(np.all(v >= -1e-4) and np.all(v <= 1 + 1e-4))

    out = srgb(1.0)
    if not fits(out):
        lo, hi = 0.0, 1.0  # binary search for the largest chroma that fits
        for _ in range(18):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if fits(srgb(mid)) else (lo, mid)
        out = srgb(lo)
    return tuple(int(round(v)) for v in np.clip(out, 0, 1) * 255)


def mix_series(rgb: RGB, other: RGB) -> list[RGB]:
    return [tuple(mixbox.lerp(rgb, other, t)) for t in MIX_STEPS]


def tints(rgb: RGB) -> list[RGB]:
    return mix_series(rgb, WHITE)


def shades(rgb: RGB) -> list[RGB]:
    return mix_series(rgb, BLACK)


def tones(rgb: RGB) -> list[RGB]:
    return mix_series(rgb, GRAY)


def sample_average(image_rgba: np.ndarray, x: float, y: float, radius: int) -> RGB | None:
    """Mean color of the square of `radius` pixels around (x, y), weighted
    by alpha so transparent edges don't drag it toward black."""
    h, w = image_rgba.shape[:2]
    cx, cy = int(math.floor(x)), int(math.floor(y))
    if not (0 <= cx < w and 0 <= cy < h):
        return None
    r = max(0, int(radius))
    patch = image_rgba[max(0, cy - r):cy + r + 1, max(0, cx - r):cx + r + 1].astype(np.float64)
    weight = patch[..., 3:4] / 255.0
    total = weight.sum()
    if total <= 0:
        return None
    mean = (patch[..., :3] * weight).sum(axis=(0, 1)) / total
    return tuple(int(round(v)) for v in mean)


def lab_image(image_rgba: np.ndarray) -> np.ndarray:
    """float32 CIELAB (D65) of an RGBA uint8 image."""
    rgb = cv2.cvtColor(image_rgba, cv2.COLOR_RGBA2RGB).astype(np.float32) / 255.0
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2Lab)


def similarity_mask(lab: np.ndarray, colors: list[RGB], tolerance: float) -> np.ndarray:
    """Pixels within `tolerance` (CIELAB distance) of any of `colors`."""
    mask = np.zeros(lab.shape[:2], dtype=bool)
    limit = float(tolerance) ** 2
    for rgb in colors:
        ref = lab_image(np.array([[[*rgb, 255]]], dtype=np.uint8))[0, 0]
        diff = lab - ref
        mask |= (diff * diff).sum(axis=2) <= limit
    return mask


def highlight_overlay(image_rgba: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Grayscale copy of the image with matching pixels painted bright
    yellow, keeping the image's own transparency."""
    gray = cv2.cvtColor(cv2.cvtColor(image_rgba, cv2.COLOR_RGBA2GRAY), cv2.COLOR_GRAY2RGB)
    out = cv2.cvtColor(gray, cv2.COLOR_RGB2RGBA)
    out[mask, :3] = HIGHLIGHT_RGB
    cv2.mixChannels([image_rgba], [out], [3, 3])
    return out
