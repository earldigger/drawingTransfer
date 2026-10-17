from canvastransfer.models import (
    Project,
    Layer,
    Transform,
    GridSettings,
    PerspectiveCorners,
    Units,
    BlendMode,
    new_id,
)


def make_layer(name="Source"):
    return Layer(id=new_id("layer"), name=name, image_filename=f"{name}.png")


def test_project_round_trip_through_dict():
    project = Project(name="My Painting", canvas_width=24, canvas_height=36, units=Units.INCHES)
    layer = make_layer("Drawing")
    layer.transform = Transform(offset_x=5, rotation_deg=3.5)
    layer.perspective_corners = PerspectiveCorners.default_for_image(800, 600)
    layer.blend_mode = BlendMode.MULTIPLY
    project.add_layer(layer)
    project.grid = GridSettings(enabled=True, rows=4, columns=5)

    restored = Project.from_dict(project.to_dict())

    assert restored.name == "My Painting"
    assert restored.canvas_width == 24
    assert restored.units == Units.INCHES
    assert len(restored.layers) == 1
    assert restored.layers[0].transform.offset_x == 5
    assert restored.layers[0].transform.rotation_deg == 3.5
    assert restored.layers[0].blend_mode == BlendMode.MULTIPLY
    assert restored.layers[0].perspective_corners.top_right == (800.0, 0.0)
    assert restored.grid.rows == 4
    assert restored.grid.columns == 5
    assert restored.active_layer_id == layer.id


def test_add_remove_layer_updates_active_layer():
    project = Project(name="P", canvas_width=10, canvas_height=10)
    a, b = make_layer("A"), make_layer("B")
    project.add_layer(a)
    project.add_layer(b)
    assert project.active_layer_id == b.id

    project.remove_layer(b.id)
    assert project.active_layer_id == a.id
    assert [l.name for l in project.layers] == ["A"]


def test_move_layer_reorders_list():
    project = Project(name="P", canvas_width=10, canvas_height=10)
    a, b, c = make_layer("A"), make_layer("B"), make_layer("C")
    for layer in (a, b, c):
        project.add_layer(layer)

    project.move_layer(c.id, 0)

    assert [l.name for l in project.layers] == ["C", "A", "B"]


def test_move_layer_unknown_id_is_noop():
    project = Project(name="P", canvas_width=10, canvas_height=10)
    a = make_layer("A")
    project.add_layer(a)

    project.move_layer("does-not-exist", 0)

    assert [l.name for l in project.layers] == ["A"]
