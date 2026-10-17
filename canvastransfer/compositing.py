"""Image processing: the role Core Image plays in the spec.

All images are handled internally as float32 RGBA arrays in the 0..1 range,
channel order R, G, B, A (NOT OpenCV's native BGR -- conversion happens at
the load/save boundary in project_io.py). This keeps perspective correction,
transforms, and blending nondestructive: layers always hold references to
their original source image plus parameters, and every function here is a
pure function from (image, params) -> new image.
"""

from __future__ import annotations

import numpy as np
import cv2

from .models import Transform, PerspectiveCorners, GridSettings, BlendMode

Size = tuple[int, int]  # (width, height)


def to_float_rgba(image_uint8: np.ndarray) -> np.ndarray:
    """Accepts HxWx3 or HxWx4 uint8 RGB(A) and returns HxWx4 float32 0..1."""
    if image_uint8.shape[2] == 3:
        h, w = image_uint8.shape[:2]
        alpha = np.full((h, w, 1), 255, dtype=np.uint8)
        image_uint8 = np.concatenate([image_uint8, alpha], axis=2)
    return image_uint8.astype(np.float32) / 255.0


def to_uint8_rgba(image_float: np.ndarray) -> np.ndarray:
    return np.clip(image_float * 255.0, 0, 255).astype(np.uint8)


def perspective_correct(image: np.ndarray, corners: PerspectiveCorners, output_size: Size) -> np.ndarray:
    """Warp the quadrilateral defined by `corners` (in source image pixel
    space) onto a rectangle of `output_size`. Input/output are float32 RGBA.
    """
    w, h = output_size
    src = np.array(corners.as_list(), dtype=np.float32)
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    return warped


def _affine_matrix(transform: Transform, image_size: Size, canvas_size: Size) -> np.ndarray:
    iw, ih = image_size
    cw, ch = canvas_size
    cx, cy = iw / 2.0, ih / 2.0

    to_origin = np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1]], dtype=np.float64)

    skew_x = np.tan(np.radians(transform.skew_x_deg))
    skew_y = np.tan(np.radians(transform.skew_y_deg))
    skew = np.array([[1, skew_x, 0], [skew_y, 1, 0], [0, 0, 1]], dtype=np.float64)

    scale = np.array(
        [[transform.scale_x, 0, 0], [0, transform.scale_y, 0], [0, 0, 1]], dtype=np.float64
    )

    theta = np.radians(transform.rotation_deg)
    c, s = np.cos(theta), np.sin(theta)
    rotate = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)

    tx = cw / 2.0 + transform.offset_x
    ty = ch / 2.0 + transform.offset_y
    to_canvas = np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]], dtype=np.float64)

    matrix_3x3 = to_canvas @ rotate @ scale @ skew @ to_origin
    return matrix_3x3[:2, :].astype(np.float32)


def apply_transform(image: np.ndarray, transform: Transform, canvas_size: Size) -> np.ndarray:
    """Place `image` (float32 RGBA, any size) onto a canvas of `canvas_size`
    applying move/scale/rotate/skew. Returns float32 RGBA at canvas_size.
    """
    h, w = image.shape[:2]
    matrix = _affine_matrix(transform, (w, h), canvas_size)
    cw, ch = canvas_size
    out = cv2.warpAffine(
        image,
        matrix,
        (cw, ch),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    return out


def blend_over(base: np.ndarray, top: np.ndarray, opacity: float, mode: BlendMode) -> np.ndarray:
    """Composite `top` over `base` (both float32 RGBA, same shape) using the
    given blend mode and layer opacity. Standard "over" alpha compositing,
    with the blend mode applied to the color term as in Core Image / most
    design tools.
    """
    top_a = top[..., 3:4] * float(opacity)
    base_rgb, base_a = base[..., :3], base[..., 3:4]
    top_rgb = top[..., :3]

    if mode == BlendMode.MULTIPLY:
        blended_rgb = base_rgb * top_rgb
    else:
        blended_rgb = top_rgb

    out_rgb = blended_rgb * top_a + base_rgb * (1 - top_a)
    out_a = top_a + base_a * (1 - top_a)
    return np.concatenate([out_rgb, out_a], axis=2)


def blank_canvas(canvas_size: Size, rgb=(1.0, 1.0, 1.0)) -> np.ndarray:
    """An opaque canvas (default white) to composite layers onto."""
    w, h = canvas_size
    canvas = np.empty((h, w, 4), dtype=np.float32)
    canvas[..., 0] = rgb[0]
    canvas[..., 1] = rgb[1]
    canvas[..., 2] = rgb[2]
    canvas[..., 3] = 1.0
    return canvas


def composite_layers(layers_bottom_to_top, canvas_size: Size) -> np.ndarray:
    """layers_bottom_to_top: iterable of (float32 RGBA image at canvas_size,
    opacity, BlendMode). Returns the composited float32 RGBA canvas.
    """
    canvas = blank_canvas(canvas_size)
    for image, opacity, mode in layers_bottom_to_top:
        canvas = blend_over(canvas, image, opacity, mode)
    return canvas


def render_grid(canvas_size: Size, grid: GridSettings) -> np.ndarray:
    """A transparent float32 RGBA image with `grid.rows` x `grid.columns`
    cells marked by division lines (e.g. rows=3, columns=3 for a 3x3 grid).
    """
    w, h = canvas_size
    out = np.zeros((h, w, 4), dtype=np.float32)
    if not grid.enabled or grid.rows < 1 or grid.columns < 1:
        return out

    color = np.array(grid.color, dtype=np.float32) / 255.0
    thickness = max(1, round(grid.thickness_px))
    out_uint8 = np.zeros((h, w, 4), dtype=np.uint8)
    bgr = (int(color[2] * 255), int(color[1] * 255), int(color[0] * 255), 255)

    for i in range(1, grid.columns):
        x = round(i * w / grid.columns)
        cv2.line(out_uint8, (x, 0), (x, h - 1), bgr, thickness)
    for i in range(1, grid.rows):
        y = round(i * h / grid.rows)
        cv2.line(out_uint8, (0, y), (w - 1, y), bgr, thickness)

    out = to_float_rgba(out_uint8[..., :4])
    out[..., 3] *= grid.opacity
    return out


def embed_on_canvas(image: np.ndarray, canvas_size: Size) -> np.ndarray:
    """Center `image` (float32 RGBA, any size) onto a transparent plane of
    `canvas_size`, cropping if larger or padding if smaller. Used so a
    layer's offset/scale/rotation always operate in canvas-pixel coordinates
    even before perspective correction has been applied to that layer.
    """
    cw, ch = canvas_size
    out = np.zeros((ch, cw, 4), dtype=np.float32)
    ih, iw = image.shape[:2]

    dst_x, dst_y = (cw - iw) // 2, (ch - ih) // 2
    src_x0, src_y0 = max(0, -dst_x), max(0, -dst_y)
    dst_x0, dst_y0 = max(0, dst_x), max(0, dst_y)
    copy_w = min(iw - src_x0, cw - dst_x0)
    copy_h = min(ih - src_y0, ch - dst_y0)
    if copy_w > 0 and copy_h > 0:
        out[dst_y0:dst_y0 + copy_h, dst_x0:dst_x0 + copy_w] = (
            image[src_y0:src_y0 + copy_h, src_x0:src_x0 + copy_w]
        )
    return out


def split_view(image_a: np.ndarray, image_b: np.ndarray, split_position: float, divider_px: int = 2) -> np.ndarray:
    """Side-by-side compare: `image_a` on the left, `image_b` on the right,
    split at `split_position` (0..1 fraction of width), with a thin divider.
    Both inputs are float32 RGBA at the same canvas size; output is opaque.
    """
    h, w = image_a.shape[:2]
    split_x = int(round(np.clip(split_position, 0.0, 1.0) * w))
    out = image_a.copy()
    out[:, split_x:] = image_b[:, split_x:]
    half = divider_px // 2
    lo, hi = max(0, split_x - half), min(w, split_x + half + 1)
    out[:, lo:hi, :3] = 1.0
    out[:, lo:hi, 3] = 1.0
    return out
