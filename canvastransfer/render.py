"""Application-level rendering: turns a ProjectDocument into a single
composited image, tying together models, project_io, and compositing.
"""

from __future__ import annotations

import numpy as np

from .models import Project, BlendMode
from .project_io import ProjectDocument
from .compositing import (
    perspective_correct,
    embed_on_canvas,
    apply_transform,
    composite_layers,
    render_grid,
    blend_over,
    blank_canvas,
    Size,
)

MAX_CANVAS_EDGE_PX = 1100


def compute_canvas_pixel_size(project: Project) -> Size:
    """Pick a working render resolution that matches the canvas's physical
    aspect ratio, independent of the units (inches vs centimeters) used.
    """
    width = max(project.canvas_width, 1e-6)
    height = max(project.canvas_height, 1e-6)
    aspect = width / height
    if aspect >= 1:
        w = MAX_CANVAS_EDGE_PX
        h = max(1, round(MAX_CANVAS_EDGE_PX / aspect))
    else:
        h = MAX_CANVAS_EDGE_PX
        w = max(1, round(MAX_CANVAS_EDGE_PX * aspect))
    return (w, h)


def render_layer(doc: ProjectDocument, layer_id: str, canvas_px_size: Size) -> np.ndarray | None:
    """Render a single layer (perspective correction + transform) onto a
    canvas-sized plane, ignoring visibility/opacity/blend.
    """
    layer = doc.project.get_layer(layer_id)
    raw = doc.get_layer_image(layer_id)
    if layer is None or raw is None:
        return None
    if layer.perspective_corners is not None:
        plane = perspective_correct(raw, layer.perspective_corners, canvas_px_size)
    else:
        plane = embed_on_canvas(raw, canvas_px_size)
    return apply_transform(plane, layer.transform, canvas_px_size)


def render_composite(doc: ProjectDocument, canvas_px_size: Size, include_grid: bool = True) -> np.ndarray:
    prepared = []
    for layer in doc.project.layers:
        if not layer.visible:
            continue
        plane = render_layer(doc, layer.id, canvas_px_size)
        if plane is not None:
            prepared.append((plane, layer.opacity, layer.blend_mode))

    composite = composite_layers(prepared, canvas_px_size)

    if include_grid and doc.project.grid.enabled:
        grid_img = render_grid(canvas_px_size, doc.project.grid)
        composite = blend_over(composite, grid_img, 1.0, BlendMode.NORMAL)

    return composite
