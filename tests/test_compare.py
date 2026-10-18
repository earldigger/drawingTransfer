from canvastransfer.compare import display_states, uses_split_line
from canvastransfer.models import Project, Layer, BlendMode, CompareMode, new_id


def make_project():
    project = Project(name="P", canvas_width=10, canvas_height=10)
    drawing = Layer(id=new_id("l"), name="drawing", image_filename="d.png", opacity=0.6, blend_mode=BlendMode.MULTIPLY)
    canvas = Layer(id=new_id("l"), name="canvas", image_filename="c.png")
    extra = Layer(id=new_id("l"), name="extra", image_filename="e.png", visible=False)
    for layer in (canvas, drawing, extra):
        project.add_layer(layer)
    project.compare_layer_a, project.compare_layer_b = drawing.id, canvas.id
    return project, drawing, canvas, extra


def test_overlay_uses_layer_settings():
    project, drawing, canvas, extra = make_project()
    states = display_states(project, True)
    assert states[drawing.id].opacity == 0.6 and states[drawing.id].blend == BlendMode.MULTIPLY
    assert states[canvas.id].visible and not states[extra.id].visible


def test_blink_alternates_solo_layers():
    project, drawing, canvas, extra = make_project()
    project.compare_mode = CompareMode.BLINK
    on, off = display_states(project, True), display_states(project, False)
    assert on[drawing.id].visible and not on[canvas.id].visible
    assert on[drawing.id].opacity == 1.0 and on[drawing.id].blend == BlendMode.NORMAL
    assert off[canvas.id].visible and not off[drawing.id].visible


def test_blink_a_only_toggles_a_and_keeps_rest_of_stack():
    project, drawing, canvas, extra = make_project()
    project.compare_mode = CompareMode.BLINK_A
    on, off = display_states(project, True), display_states(project, False)
    assert on[drawing.id].visible and on[drawing.id].blend == BlendMode.MULTIPLY and on[drawing.id].opacity == 0.6
    assert not off[drawing.id].visible
    for states in (on, off):
        assert states[canvas.id].visible
        assert not states[extra.id].visible


def test_blink_a_shows_a_even_if_its_eye_is_off():
    project, drawing, canvas, extra = make_project()
    drawing.visible = False
    project.compare_mode = CompareMode.BLINK_A
    assert display_states(project, True)[drawing.id].visible


def test_split_clips_a_left_b_right_and_hides_others():
    project, drawing, canvas, extra = make_project()
    project.compare_mode = CompareMode.SPLIT
    states = display_states(project, True)
    assert states[drawing.id].clip == "left" and states[canvas.id].clip == "right"
    assert not states[extra.id].visible
    assert uses_split_line(project)


def test_split_with_same_layer_twice_falls_back_to_overlay():
    project, drawing, canvas, extra = make_project()
    project.compare_mode = CompareMode.SPLIT
    project.compare_layer_b = drawing.id
    assert display_states(project, True)[drawing.id].clip is None
    assert not uses_split_line(project)


def test_missing_compare_layer_falls_back_to_overlay():
    project, drawing, canvas, extra = make_project()
    project.compare_mode = CompareMode.BLINK
    project.compare_layer_b = "deleted"
    assert display_states(project, False)[drawing.id].visible
