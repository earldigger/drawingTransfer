import os

import cv2
import numpy as np

from canvastransfer.models import Project, Layer, Units, new_id
from canvastransfer.project_io import ProjectDocument, save_project, load_project, autosave, load_image_rgba


def make_doc():
    project = Project(name="Still Life", canvas_width=18, canvas_height=24, units=Units.INCHES)
    layer = Layer(id=new_id("layer"), name="Drawing", image_filename="drawing.png")
    layer.quad = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
    project.add_layer(layer)

    image = np.zeros((20, 30, 4), dtype=np.uint8)
    image[..., 0] = 191
    image[..., 3] = 255

    doc = ProjectDocument(project=project)
    doc.set_layer_image(layer.id, image)
    return doc, layer, image


def test_save_creates_expected_package_layout(tmp_path):
    doc, layer, _ = make_doc()
    package = tmp_path / "Still Life.ctproj"
    save_project(doc, package)
    assert (package / "project.json").exists()
    assert (package / "images" / "drawing.png").exists()
    assert doc.package_dir == package


def test_load_round_trips_metadata_and_pixels(tmp_path):
    doc, layer, image = make_doc()
    package = tmp_path / "p.ctproj"
    save_project(doc, package)

    loaded = load_project(package)

    loaded_layer = loaded.project.layers[0]
    assert loaded_layer.quad == layer.quad
    loaded_image = loaded.get_layer_image(loaded_layer.id)
    assert loaded_image.dtype == np.uint8
    assert np.array_equal(loaded_image, image)


def test_resave_does_not_rewrite_source_images(tmp_path):
    doc, _, _ = make_doc()
    package = tmp_path / "p.ctproj"
    save_project(doc, package)
    image_file = package / "images" / "drawing.png"
    os.utime(image_file, (1, 1))

    doc.project.name = "renamed"
    save_project(doc, package)

    assert image_file.stat().st_mtime == 1
    assert load_project(package).project.name == "renamed"


def test_deleted_layer_image_is_removed_on_save(tmp_path):
    doc, layer, _ = make_doc()
    package = tmp_path / "p.ctproj"
    save_project(doc, package)
    doc.project.remove_layer(layer.id)
    save_project(doc, package)
    assert not (package / "images" / "drawing.png").exists()


def test_autosave_noop_before_first_save():
    doc, _, _ = make_doc()
    assert autosave(doc) is False


def test_autosave_saves_in_place_after_first_save(tmp_path):
    doc, _, _ = make_doc()
    package = tmp_path / "p.ctproj"
    save_project(doc, package)
    doc.project.name = "Still Life (renamed)"
    assert autosave(doc) is True
    assert load_project(package).project.name == "Still Life (renamed)"


def test_load_image_handles_gray_jpeg_and_alpha_png(tmp_path):
    gray = np.full((5, 7), 90, dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "g.jpg"), gray)
    rgba = load_image_rgba(tmp_path / "g.jpg")
    assert rgba.shape == (5, 7, 4) and rgba[0, 0, 3] == 255

    bgra = np.zeros((3, 3, 4), dtype=np.uint8)
    bgra[..., 0] = 255  # blue in OpenCV's order
    bgra[..., 3] = 100
    cv2.imwrite(str(tmp_path / "a.png"), bgra)
    rgba = load_image_rgba(tmp_path / "a.png")
    assert tuple(rgba[0, 0]) == (0, 0, 255, 100)
