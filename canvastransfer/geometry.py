"""Pure 2D geometry for placing layers on the canvas and for the
interactive transform tool. No Qt or numpy, so it is easy to test and to
port.

A quad is four canvas-pixel points [TL, TR, BR, BL]: where the layer
image's own corners land. Edge i runs from corner i to corner i+1
(0 = top, 1 = right, 2 = bottom, 3 = left in the image's own orientation).
Every drag is computed from the quad as it was when the drag started, so
repeated mouse-move events never accumulate rounding drift.
"""

from __future__ import annotations

import math
from enum import Enum

Point = tuple[float, float]
Quad = list[Point]

MAX_CANVAS_EDGE_PX = 1100
MIN_SCALE = 0.02
MIN_AREA_PX = 16.0


class TransformMode(str, Enum):
    UNIFORM = "uniform"
    FREE = "free"
    SKEW = "skew"
    DISTORT = "distort"


# Handles: ("move",), ("rotate",), ("corner", i), ("edge", i)
Handle = tuple


def canvas_pixel_size(width: float, height: float, max_edge: int = MAX_CANVAS_EDGE_PX) -> tuple[int, int]:
    """Scene size for the canvas: physical aspect ratio, unit-independent."""
    width = max(width, 1e-6)
    height = max(height, 1e-6)
    aspect = width / height
    if aspect >= 1:
        return max_edge, max(1, round(max_edge / aspect))
    return max(1, round(max_edge * aspect)), max_edge


def canvas_quad(canvas_w: float, canvas_h: float) -> Quad:
    return [(0.0, 0.0), (canvas_w, 0.0), (canvas_w, canvas_h), (0.0, canvas_h)]


def fit_quad(image_w: float, image_h: float, canvas_w: float, canvas_h: float) -> Quad:
    """Largest aspect-preserving placement of the image inside the canvas,
    centered -- so a freshly imported image is never cropped.
    """
    s = min(canvas_w / image_w, canvas_h / image_h)
    w, h = image_w * s, image_h * s
    x0, y0 = (canvas_w - w) / 2, (canvas_h - h) / 2
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]


def normalize_quad(quad: Quad, canvas_w: float, canvas_h: float) -> list[Point]:
    return [(x / canvas_w, y / canvas_h) for x, y in quad]


def denormalize_quad(quad: list[Point], canvas_w: float, canvas_h: float) -> Quad:
    return [(x * canvas_w, y * canvas_h) for x, y in quad]


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Point, s: float) -> Point:
    return (a[0] * s, a[1] * s)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def centroid(quad: Quad) -> Point:
    return (sum(p[0] for p in quad) / 4.0, sum(p[1] for p in quad) / 4.0)


def edge_midpoints(quad: Quad) -> list[Point]:
    return [_mul(_add(quad[i], quad[(i + 1) % 4]), 0.5) for i in range(4)]


def area(quad: Quad) -> float:
    s = 0.0
    for i in range(4):
        x0, y0 = quad[i]
        x1, y1 = quad[(i + 1) % 4]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def is_convex(quad: Quad) -> bool:
    """True for a non-degenerate convex quad, either winding (a flipped
    layer winds the other way)."""
    signs = []
    for i in range(4):
        a, b, c = quad[i], quad[(i + 1) % 4], quad[(i + 2) % 4]
        signs.append(_cross(_sub(b, a), _sub(c, b)))
    return (all(s > 0 for s in signs) or all(s < 0 for s in signs)) and area(quad) >= MIN_AREA_PX


def point_in_quad(quad: Quad, p: Point) -> bool:
    signs = [_cross(_sub(quad[(i + 1) % 4], quad[i]), _sub(p, quad[i])) for i in range(4)]
    return all(s >= 0 for s in signs) or all(s <= 0 for s in signs)


def rotation_handle(quad: Quad, offset: float) -> tuple[Point, Point]:
    """(handle position, edge midpoint it hangs from). Placed off the edge
    that is currently highest on screen, so it stays on top after flips
    and rotations."""
    mids = edge_midpoints(quad)
    mid = min(mids, key=lambda m: m[1])
    c = centroid(quad)
    d = _sub(mid, c)
    length = math.hypot(*d) or 1.0
    return _add(mid, _mul(d, offset / length)), mid


def translate(quad: Quad, delta: Point) -> Quad:
    return [_add(p, delta) for p in quad]


def rotate(quad: Quad, angle_rad: float, center: Point) -> Quad:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    out = []
    for p in quad:
        dx, dy = _sub(p, center)
        out.append((center[0] + dx * c - dy * s, center[1] + dx * s + dy * c))
    return out


def scale_about(quad: Quad, anchor: Point, s: float) -> Quad:
    return [_add(anchor, _mul(_sub(p, anchor), s)) for p in quad]


def flip_horizontal(quad: Quad) -> Quad:
    """Mirror the image inside the same box (swap left and right corners)."""
    return [quad[1], quad[0], quad[3], quad[2]]


def flip_vertical(quad: Quad) -> Quad:
    return [quad[3], quad[2], quad[1], quad[0]]


def _basis(quad: Quad) -> tuple[Point, Point]:
    """The layer's own x (top edge) and y (left edge) directions."""
    return _sub(quad[1], quad[0]), _sub(quad[3], quad[0])


def _to_basis(v: Point, u_axis: Point, v_axis: Point) -> Point | None:
    det = _cross(u_axis, v_axis)
    if abs(det) < 1e-9:
        return None
    return (_cross(v, v_axis) / det, _cross(u_axis, v) / det)


def _from_basis(c: Point, u_axis: Point, v_axis: Point) -> Point:
    return _add(_mul(u_axis, c[0]), _mul(v_axis, c[1]))


def _ratio(new: float, old: float) -> float:
    if abs(old) < 1e-9:
        return 1.0
    return max(MIN_SCALE, new / old)


def _uniform(quad: Quad, anchor: Point, start: Point, current: Point) -> Quad:
    d0, d1 = _sub(start, anchor), _sub(current, anchor)
    denom = _dot(d0, d0)
    s = max(MIN_SCALE, _dot(d1, d0) / denom) if denom > 1e-9 else 1.0
    return scale_about(quad, anchor, s)


def _free(quad: Quad, anchor: Point, start: Point, current: Point, lock_u: bool, lock_v: bool) -> Quad | None:
    u_axis, v_axis = _basis(quad)
    c0 = _to_basis(_sub(start, anchor), u_axis, v_axis)
    c1 = _to_basis(_sub(current, anchor), u_axis, v_axis)
    if c0 is None or c1 is None:
        return None
    su = 1.0 if lock_u else _ratio(c1[0], c0[0])
    sv = 1.0 if lock_v else _ratio(c1[1], c0[1])
    out = []
    for p in quad:
        c = _to_basis(_sub(p, anchor), u_axis, v_axis)
        out.append(_add(anchor, _from_basis((c[0] * su, c[1] * sv), u_axis, v_axis)))
    return out


def _skew_edge(quad: Quad, edge: int, delta: Point) -> Quad:
    """Slide one edge along its own direction: a shear."""
    a, b = edge, (edge + 1) % 4
    e = _sub(quad[b], quad[a])
    length = math.hypot(*e)
    if length < 1e-9:
        return list(quad)
    e_hat = _mul(e, 1.0 / length)
    shift = _mul(e_hat, _dot(delta, e_hat))
    out = list(quad)
    out[a] = _add(out[a], shift)
    out[b] = _add(out[b], shift)
    return out


def apply_drag(mode: TransformMode, handle: Handle, quad: Quad, start: Point, current: Point) -> Quad | None:
    """New quad for dragging `handle` from `start` to `current` (canvas px),
    starting from `quad`. Returns None if the result would fold over or
    collapse, so the caller can keep the last valid quad.
    """
    delta = _sub(current, start)
    kind = handle[0]

    if kind == "move":
        result = translate(quad, delta)
    elif kind == "rotate":
        c = centroid(quad)
        v0, v1 = _sub(start, c), _sub(current, c)
        angle = math.atan2(v1[1], v1[0]) - math.atan2(v0[1], v0[0])
        result = rotate(quad, angle, c)
    elif kind == "corner":
        i = handle[1]
        if mode == TransformMode.DISTORT:
            result = list(quad)
            result[i] = _add(quad[i], delta)
        elif mode == TransformMode.UNIFORM:
            result = _uniform(quad, quad[(i + 2) % 4], start, current)
        else:  # FREE and SKEW: corners scale each axis independently
            result = _free(quad, quad[(i + 2) % 4], start, current, False, False)
    elif kind == "edge":
        i = handle[1]
        anchor = edge_midpoints(quad)[(i + 2) % 4]
        if mode == TransformMode.DISTORT:
            result = list(quad)
            for j in (i, (i + 1) % 4):
                result[j] = _add(quad[j], delta)
        elif mode == TransformMode.SKEW:
            result = _skew_edge(quad, i, delta)
        elif mode == TransformMode.UNIFORM:
            result = _uniform(quad, anchor, start, current)
        else:  # FREE: top/bottom edges stretch height only, left/right width only
            horizontal_edge = i in (0, 2)
            result = _free(quad, anchor, start, current, lock_u=horizontal_edge, lock_v=not horizontal_edge)
    else:
        raise ValueError(f"unknown handle {handle!r}")

    if result is None or not is_convex(result):
        return None
    return result
