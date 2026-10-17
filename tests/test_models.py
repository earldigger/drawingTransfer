from canvastransfer.models import (
    Project,
    Layer,
    GridSettings,
    PerspectiveCorners,
    Units,
    BlendMode,
    CompareMode,
    new_id,
)


def make_layer(name="Source"):
    return Layer(id=new_id("layer"), name=name, image_filename=f"{name}.png")


def test_project_round_trip_through_dict():
    project = Project(name="My Painting", canvas_width=24, canvas_height=36, units=Units.INCHES)
    layer = make_layer("Drawing")
    layer.quad = [(0.1, 0.2), (0.9, 0.2), (0.9, 0.8), (0.1, 0.8)]
    layer.perspective_corners = PerspectiveCorners.default_for_image(800, 600)
    layer.perspective_fill_canvas = True
    layer.blend_mode = BlendMode.MULTIPLY
    layer.contrast = 0.4
    layer.invert = True
    project.add_layer(layer)
    project.grid = GridSettings(enabled=True, rows=4, columns=5, color=(10, 20, 30))
    project.compare_mode = CompareMode.BLINK_A

    restored = Project.from_dict(project.to_dict())

    r = restored.layers[0]
    assert restored.name == "My Painting" and restored.units == Units.INCHES
    assert r.quad == layer.quad
    assert r.blend_mode == BlendMode.MULTIPLY
    assert r.perspective_corners.top_right == (800.0, 0.0)
    assert r.perspective_fill_canvas and r.invert and r.contrast == 0.4
    assert restored.grid.color == (10, 20, 30) and restored.grid.columns == 5
    assert restored.compare_mode == CompareMode.BLINK_A
    assert restored.active_layer_id == layer.id


def test_unplaced_layer_round_trips_as_none():
    layer = make_layer()
    assert Layer.from_dict(layer.to_dict()).quad is None


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
    project.add_layer(make_layer("A"))
    project.move_layer("does-not-exist", 0)
    assert [l.name for l in project.layers] == ["A"]
