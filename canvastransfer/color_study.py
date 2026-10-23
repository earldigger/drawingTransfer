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
from dataclasses import dataclass
from functools import lru_cache

import cv2
import mixbox
import numpy as np

RGB = tuple[int, int, int]

# one highlight color per swatch (by its number), bright and far apart in hue so
# several highlighted ranges can be told apart over the grayscale image
HIGHLIGHT_COLORS = (
    (255, 236, 0),    # yellow
    (0, 224, 255),    # cyan
    (255, 60, 200),   # magenta
    (90, 255, 70),    # green
    (255, 140, 0),    # orange
    (70, 120, 255),   # blue
    (255, 40, 40),    # red
    (185, 95, 255),   # violet
)
HIGHLIGHT_RGB = HIGHLIGHT_COLORS[0]
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


@lru_cache(maxsize=1)
def _srgb_to_xyz_d50() -> tuple[np.ndarray, np.ndarray]:
    """Linear-sRGB-to-XYZ (Bradford-adapted to D50) matrix and the D50 white."""
    c, ill = _colour(), _illuminants()
    m = c.sRGB_to_XYZ(np.eye(3), illuminant=ill["D50"], chromatic_adaptation_transform="Bradford").T
    return m, c.xy_to_XYZ(ill["D50"])


def srgb_to_lab_d50(rgb01: np.ndarray) -> np.ndarray:
    """Many sRGB colors (floats 0..1, shape (..., 3)) to CIELAB D50 at once.
    Same result as lab_d50, written out in NumPy because it runs on every
    candidate mix when searching for recipes."""
    m, white = _srgb_to_xyz_d50()
    rgb01 = np.asarray(rgb01, dtype=np.float64)
    linear = np.where(rgb01 <= 0.04045, rgb01 / 12.92, ((rgb01 + 0.055) / 1.055) ** 2.4)
    t = (linear @ m.T) / white
    f = np.where(t > (6 / 29) ** 3, np.cbrt(t), t / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def lab_d50_to_srgb(lab) -> tuple[RGB, bool]:
    """Screen color for a CIELAB D50 value, and whether it fits on screen.
    Colors outside sRGB (many cadmiums, for example) are clipped."""
    c, ill = _colour(), _illuminants()
    xyz = c.Lab_to_XYZ(np.asarray(lab, dtype=float), ill["D50"])
    rgb = c.XYZ_to_sRGB(xyz, illuminant=ill["D50"], chromatic_adaptation_transform="Bradford")
    in_gamut = bool(np.all(rgb >= -0.5 / 255) and np.all(rgb <= 1 + 0.5 / 255))
    return tuple(int(round(v)) for v in np.clip(rgb, 0, 1) * 255), in_gamut


def delta_e(lab1, lab2) -> np.ndarray:
    """CIEDE2000 color difference; about 1 is just visible side by side."""
    return _colour().delta_E(lab1, lab2, method="CIE 2000")


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


def highlight_color(index: int) -> RGB:
    """The highlight color for swatch number index + 1 (repeats after eight)."""
    return HIGHLIGHT_COLORS[index % len(HIGHLIGHT_COLORS)]


def similarity_labels(lab: np.ndarray, colors: list[RGB], tolerance: float) -> np.ndarray:
    """For each pixel, the index of the closest of `colors` within
    `tolerance`, or -1. Where ranges overlap, the closer swatch wins, so
    each pixel shows one swatch's highlight."""
    labels = np.full(lab.shape[:2], -1, dtype=np.int16)
    best = np.full(lab.shape[:2], float(tolerance) ** 2, dtype=np.float32)
    for i, rgb in enumerate(colors):
        ref = lab_image(np.array([[[*rgb, 255]]], dtype=np.uint8))[0, 0]
        diff = lab - ref
        dist = (diff * diff).sum(axis=2)
        closer = dist <= best
        labels[closer] = i
        best[closer] = dist[closer]
    return labels


def highlight_overlay(image_rgba: np.ndarray, mask: np.ndarray, colors: list[RGB] | None = None) -> np.ndarray:
    """Grayscale copy of the image with matching pixels painted bright,
    keeping the image's own transparency. `mask` is either a boolean mask
    (painted yellow) or labels from similarity_labels, painted with
    `colors[label]`."""
    if mask.dtype == bool:
        mask, colors = np.where(mask, 0, -1), [HIGHLIGHT_RGB]
    gray = cv2.cvtColor(cv2.cvtColor(image_rgba, cv2.COLOR_RGBA2GRAY), cv2.COLOR_GRAY2RGB)
    out = cv2.cvtColor(gray, cv2.COLOR_RGB2RGBA)
    for i, rgb in enumerate(colors):
        out[mask == i, :3] = rgb
    cv2.mixChannels([image_rgba], [out], [3, 3])
    return out



# -- simplify ------------------------------------------------------------------

@dataclass
class Simplified:
    """An image reduced to a few flat colors (or values)."""

    image: np.ndarray  # RGBA uint8, the same size as the input
    labels: np.ndarray  # int16 per pixel: index into colors, -1 where transparent
    colors: list[RGB]  # darkest first
    shares: list[float]  # fraction of the visible pixels each color covers


SIMPLIFY_SAMPLE = 20_000  # pixels used to find the colors; all pixels are then assigned


def value_scale(steps: int) -> list[RGB]:
    """`steps` grays splitting lightness (CIELAB L*, close to Munsell value
    x 10) into equal bands from black to white, each at its band's middle:
    5 steps are L* 10, 30, 50, 70, 90."""
    centers = (np.arange(steps) + 0.5) * 100.0 / steps
    lab = np.column_stack([centers, np.zeros(steps), np.zeros(steps)]).reshape(1, -1, 3).astype(np.float32)
    srgb = cv2.cvtColor(lab, cv2.COLOR_Lab2RGB)[0]
    return [tuple(int(round(v)) for v in np.clip(c, 0, 1) * 255) for c in srgb]


def simplify(image_rgba: np.ndarray, count: int, smoothing: int = 2, values: bool = False,
             fixed_scale: bool = False) -> Simplified:
    """Reduce the image to `count` colors, or `count` gray values when
    `values`. Smoothing (0..6) first flattens texture and noise, then
    removes specks from the result, so shapes read as simple masses.
    Colors are found by k-means clustering in CIELAB, so they are the
    image's own dominant colors, not a fixed palette. With `fixed_scale`
    the values are instead equal steps from black to white (value_scale),
    the same for every image; steps the image doesn't reach cover 0%."""
    rgb = np.ascontiguousarray(image_rgba[..., :3])
    alpha = image_rgba[..., 3]
    if smoothing > 0:
        rgb = cv2.medianBlur(rgb, 2 * smoothing + 1)
        rgb = cv2.bilateralFilter(rgb, 5 + 2 * smoothing, 10 + 8 * smoothing, 5 + 3 * smoothing)
    # 8-bit Lab is ~50x faster than float and plenty for clustering; rescale to L 0..100, a/b centered
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2Lab).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1:] -= 128.0
    visible = alpha > 0
    labels = np.full(alpha.shape, -1, dtype=np.int16)
    if values and fixed_scale:
        return _fixed_values(image_rgba, lab[..., 0], visible, labels, count, smoothing)
    features = lab[visible][:, :1] if values else lab[visible]
    if len(features) == 0:
        return Simplified(image_rgba.copy(), labels, [], [])
    rng = np.random.default_rng(0)
    sample = features if len(features) <= SIMPLIFY_SAMPLE else features[rng.choice(len(features), SIMPLIFY_SAMPLE, replace=False)]
    k = int(max(1, min(count, len(sample))))
    cv2.setRNGSeed(1)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 0.2)
    _, _, centers = cv2.kmeans(np.ascontiguousarray(sample, dtype=np.float32), k, None, criteria, 1,
                               cv2.KMEANS_PP_CENTERS)
    centers = centers[np.argsort(centers[:, 0])]  # darkest first
    assigned = np.zeros(len(features), dtype=np.int16)
    best = np.full(len(features), np.inf, dtype=np.float32)
    for i, c in enumerate(centers):  # one center at a time keeps memory small
        d = ((features - c) ** 2).sum(axis=1)
        closer = d < best
        assigned[closer] = i
        best[closer] = d[closer]
    used = np.flatnonzero(np.bincount(assigned, minlength=k))  # an image with fewer colors than asked
    centers = centers[used]
    k = len(used)
    assigned = np.searchsorted(used, assigned).astype(np.int16)
    labels[visible] = assigned
    if smoothing > 0:  # remove specks; labels are ordered by lightness, so the median picks a neighbor
        cleaned = cv2.medianBlur((labels + 1).astype(np.uint8), 3 if smoothing < 4 else 5).astype(np.int16) - 1
        labels = np.where(visible, np.maximum(cleaned, 0), -1).astype(np.int16)
    lab_centers = np.column_stack([centers[:, 0], np.zeros(k), np.zeros(k)]) if values else centers
    srgb = cv2.cvtColor(lab_centers.reshape(1, -1, 3).astype(np.float32), cv2.COLOR_Lab2RGB)[0]  # float Lab here
    colors = [tuple(int(round(v)) for v in np.clip(c, 0, 1) * 255) for c in srgb]
    palette = np.array(colors, dtype=np.uint8)
    out = image_rgba.copy()
    out[visible, :3] = palette[labels[visible]]
    counts = np.bincount(labels[visible], minlength=k)
    shares = (counts / max(1, counts.sum())).tolist()
    return Simplified(out, labels, colors, shares)


def _fixed_values(image_rgba, lightness, visible, labels, steps, smoothing) -> Simplified:
    band = np.clip((lightness * steps / 100.0).astype(np.int16), 0, steps - 1)
    labels[visible] = band[visible]
    if smoothing > 0:
        # fixed thresholds split a surface that sits right on a band edge into specks,
        # so clean up harder than the fitted modes do
        size = 3 if smoothing == 1 else (5 if smoothing < 4 else 7)
        cleaned = cv2.medianBlur((labels + 1).astype(np.uint8), size).astype(np.int16) - 1
        labels = np.where(visible, np.maximum(cleaned, 0), -1).astype(np.int16)
    colors = value_scale(steps)
    out = image_rgba.copy()
    out[visible, :3] = np.array(colors, dtype=np.uint8)[labels[visible]]
    counts = np.bincount(labels[visible], minlength=steps)
    return Simplified(out, labels, colors, (counts / max(1, counts.sum())).tolist())


def region_points(labels: np.ndarray, count: int) -> list[tuple[float, float] | None]:
    """For each color of a simplified image, a spot well inside its largest
    area, as (u, v) fractions of the image: where to put its swatch marker."""
    h, w = labels.shape
    points: list[tuple[float, float] | None] = []
    for i in range(count):
        mask = (labels == i).astype(np.uint8)
        if not mask.any():
            points.append(None)
            continue
        dist = cv2.distanceTransform(np.pad(mask, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
        y, x = np.unravel_index(int(dist.argmax()), dist.shape)
        points.append(((x + 0.5) / w, (y + 0.5) / h))
    return points
