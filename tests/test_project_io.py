import numpy as np

from canvastransfer.models import Project, Layer, Units, Transform, new_id
from canvastransfer.project_io import ProjectDocument, save_project, load_project, autosave


def make_doc(tmp_path):
    project = Project(name="Still Life", canvas_width=18, canvas_height=24, units=Units.INCHES)
    layer = Layer(id=new_id("layer"), name="Drawing", image_filename="drawing.png")
    layer.transform = Transform(offset_x=3.0, rotation_deg=2.0)
    project.add_layer(layer)

    image = np.zeros((20, 30, 4), dtype=np.float32)
    image[..., 0] = 0.75  # red channel, distinguishable after round trip
    image[..., 3] = 1.0

    doc = ProjectDocument(project=project)
    doc.set_layer_image(layer.id, image)
    return doc, layer.id, image


def test_save_creates_expected_package_layout(tmp_path):
    doc, layer_id, _ = make_doc(tmp_path)
    package = tmp_path / "Still Life.ctproj"

    save_project(doc, package)

    assert (package / "project.json").exists()
    assert (package / "images" / "drawing.png").exists()
    assert doc.package_dir == package


def test_load_project_round_trips_metadata_and_pixels(tmp_path):
    doc, layer_id, image = make_doc(tmp_path)
    package = tmp_path / "Still Life.ctproj"
    save_project(doc, package)

    loaded = load_project(package)

    assert loaded.project.name == "Still Life"
    assert loaded.project.canvas_width == 18
    assert len(loaded.project.layers) == 1
    loaded_layer = loaded.project.layers[0]
    assert loaded_layer.transform.offset_x == 3.0
    assert loaded_layer.transform.rotation_deg == 2.0

    loaded_image = loaded.get_layer_image(loaded_layer.id)
    assert loaded_image is not None
    assert loaded_image.shape == image.shape
    assert np.allclose(loaded_image[..., 0], 0.75, atol=0.01)
    assert np.allclose(loaded_image[..., 3], 1.0, atol=0.01)


def test_autosave_noop_before_first_save(tmp_path):
    doc, _, _ = make_doc(tmp_path)
    assert autosave(doc) is False


def test_autosave_saves_in_place_after_first_save(tmp_path):
    doc, layer_id, _ = make_doc(tmp_path)
    package = tmp_path / "Still Life.ctproj"
    save_project(doc, package)

    doc.project.name = "Still Life (renamed)"
    assert autosave(doc) is True

    reloaded = load_project(package)
    assert reloaded.project.name == "Still Life (renamed)"
