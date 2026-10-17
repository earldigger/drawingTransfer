import numpy as np

from canvastransfer.models import Project, Layer, Transform, GridSettings, BlendMode, Units, new_id
from canvastransfer.project_io import ProjectDocument
from canvastransfer.render import compute_canvas_pixel_size, render_composite, render_layer
from canvastransfer.compositing import embed_on_canvas


def test_compute_canvas_pixel_size_preserves_aspect_ratio():
    project = Project(name="P", canvas_width=16, canvas_height=20, units=Units.INCHES)
    w, h = compute_canvas_pixel_size(project)
    assert abs((w / h) - (16 / 20)) < 0.01


def test_embed_on_canvas_centers_smaller_image():
    img = np.ones((4, 4, 4), dtype=np.float32)
    out = embed_on_canvas(img, (10, 10))
    assert out.shape == (10, 10, 4)
    assert out[5, 5, 3] == 1.0  # center is opaque
    assert out[0, 0, 3] == 0.0  # corner stays transparent


def test_embed_on_canvas_crops_larger_image():
    img = np.ones((20, 20, 4), dtype=np.float32)
    out = embed_on_canvas(img, (10, 10))
    assert out.shape == (10, 10, 4)
    assert np.all(out[..., 3] == 1.0)


def test_render_composite_empty_project_is_blank():
    project = Project(name="Empty", canvas_width=10, canvas_height=10)
    doc = ProjectDocument(project=project)
    out = render_composite(doc, (20, 20))
    assert np.allclose(out[..., :3], 1.0)  # blank white canvas


def test_render_composite_respects_visibility():
    project = Project(name="P", canvas_width=10, canvas_height=10)
    layer = Layer(id=new_id("layer"), name="L", image_filename="l.png", visible=False)
    project.add_layer(layer)
    doc = ProjectDocument(project=project)
    doc.set_layer_image(layer.id, np.zeros((10, 10, 4), dtype=np.float32) + [0, 0, 0, 1])

    out = render_composite(doc, (10, 10))

    assert np.allclose(out[..., :3], 1.0)  # hidden layer never shows


def test_render_composite_includes_grid_when_enabled():
    project = Project(name="P", canvas_width=10, canvas_height=10)
    project.grid = GridSettings(enabled=True, rows=2, columns=2, opacity=1.0, thickness_px=1)
    doc = ProjectDocument(project=project)

    out = render_composite(doc, (20, 20))

    assert out[..., 3].sum() > 0 or (out[10, :, :3] < 0.99).any()


def test_render_layer_missing_layer_returns_none():
    project = Project(name="P", canvas_width=10, canvas_height=10)
    doc = ProjectDocument(project=project)
    assert render_layer(doc, "nope", (10, 10)) is None
