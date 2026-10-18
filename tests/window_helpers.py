import numpy as np

from canvastransfer.models import Layer, Project, new_id
from canvastransfer.project_io import ProjectDocument


def make_window_with_layers(*sizes):
    """A MainWindow showing a fresh project with one gray layer per (w, h)."""
    from canvastransfer.ui.main_window import MainWindow

    project = Project(name="T", canvas_width=10, canvas_height=10)
    doc = ProjectDocument(project)
    layers = []
    for i, (w, h) in enumerate(sizes):
        layer = Layer(id=new_id("l"), name=f"L{i}", image_filename=f"{i}.png")
        img = np.zeros((h, w, 4), dtype=np.uint8)
        img[..., :3] = 100
        img[..., 3] = 255
        doc.set_layer_image(layer.id, img)
        project.add_layer(layer)
        layers.append(layer)
    window = MainWindow()
    window._set_document(doc)
    return window, layers
