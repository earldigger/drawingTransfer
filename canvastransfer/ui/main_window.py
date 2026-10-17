from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QDockWidget,
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QFileDialog,
    QMessageBox,
)

from ..models import Project, Layer, Transform, CompareMode, BlendMode, new_id
from ..project_io import ProjectDocument, save_project, load_project, autosave
from ..render import compute_canvas_pixel_size, render_composite, render_layer
from ..compositing import composite_layers, blank_canvas, split_view

from .canvas_view import CanvasView
from .layers_panel import LayersPanel
from .transform_panel import TransformPanel
from .grid_panel import GridPanel
from .compare_panel import ComparePanel
from .perspective_dialog import PerspectiveDialog
from .new_project_dialog import NewProjectDialog
from .image_qt import rgba_float_to_qpixmap

IMAGE_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Canvas Transfer (prototype)")
        self.resize(1300, 850)

        self.doc: ProjectDocument | None = None
        self._blink_showing_a = True
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._on_blink_tick)

        self.canvas_view = CanvasView()
        self.setCentralWidget(self.canvas_view)
        self.canvas_view.layerDragDelta.connect(self._on_canvas_drag)
        self.canvas_view.dragFinished.connect(self._autosave)

        self.layers_panel = LayersPanel()
        self.transform_panel = TransformPanel()
        self.grid_panel = GridPanel()
        self.compare_panel = ComparePanel()
        self._build_side_dock()
        self._build_menu()
        self._wire_panels()

        self.statusBar().showMessage("Create or open a project to begin.")
        self._update_enabled_state()

    # -- layout -------------------------------------------------------

    def _build_side_dock(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        for panel in (self.layers_panel, self.transform_panel, self.grid_panel, self.compare_panel):
            layout.addWidget(panel)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)

        dock = QDockWidget("Workspace", self)
        dock.setWidget(scroll)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("New Project…", self._new_project)
        file_menu.addAction("Open Project…", self._open_project)
        file_menu.addAction("Save", self._save_project)
        file_menu.addAction("Save As…", self._save_project_as)
        file_menu.addSeparator()
        file_menu.addAction("Add Image Layer…", self._import_image)

    def _wire_panels(self) -> None:
        lp = self.layers_panel
        lp.layerSelected.connect(self._on_layer_selected)
        lp.layerVisibilityToggled.connect(self._on_layer_visibility_toggled)
        lp.layerOpacityChanged.connect(self._on_layer_opacity_changed)
        lp.layerBlendModeChanged.connect(self._on_layer_blend_mode_changed)
        lp.addLayerRequested.connect(self._import_image)
        lp.deleteLayerRequested.connect(self._on_delete_layer)
        lp.moveLayerUpRequested.connect(lambda lid: self._on_move_layer(lid, +1))
        lp.moveLayerDownRequested.connect(lambda lid: self._on_move_layer(lid, -1))
        lp.renameLayerRequested.connect(self._on_rename_layer)
        lp.perspectiveCorrectRequested.connect(self._on_perspective_correct)

        self.transform_panel.transformChanged.connect(self._on_transform_changed)
        self.grid_panel.gridChanged.connect(self._on_grid_changed)
        self.compare_panel.settingsChanged.connect(self._on_compare_changed)

    def _update_enabled_state(self) -> None:
        has_project = self.doc is not None
        self.layers_panel.setEnabled(has_project)
        self.grid_panel.setEnabled(has_project)
        self.compare_panel.setEnabled(has_project)

    # -- project lifecycle ---------------------------------------------

    def _new_project(self) -> None:
        dialog = NewProjectDialog(self)
        if dialog.exec() != NewProjectDialog.Accepted:
            return
        name, width, height, units = dialog.values()
        project = Project(name=name, canvas_width=width, canvas_height=height, units=units)
        self.doc = ProjectDocument(project=project)
        self._blink_showing_a = True
        self.blink_timer.stop()
        self._refresh_all()
        self.statusBar().showMessage(f"New project '{name}' ({width}x{height} {units.value}) -- not yet saved.")

    def _open_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Project (.ctproj folder)")
        if not path:
            return
        try:
            self.doc = load_project(path)
        except Exception as exc:  # surface to the user rather than crash
            QMessageBox.critical(self, "Open Project Failed", str(exc))
            return
        self._blink_showing_a = True
        self.blink_timer.stop()
        self._refresh_all()
        self.statusBar().showMessage(f"Opened '{self.doc.project.name}' from {path}")

    def _save_project(self) -> None:
        if self.doc is None:
            return
        if self.doc.package_dir is None:
            self._save_project_as()
            return
        save_project(self.doc, self.doc.package_dir)
        self.statusBar().showMessage(f"Saved to {self.doc.package_dir}")

    def _save_project_as(self) -> None:
        if self.doc is None:
            return
        suggested = f"{self.doc.project.name}.ctproj"
        path, _ = QFileDialog.getSaveFileName(self, "Save Project As", suggested, "Canvas Transfer Project (*.ctproj)")
        if not path:
            return
        save_project(self.doc, path)
        self.statusBar().showMessage(f"Saved to {path}")

    def _autosave(self) -> None:
        if self.doc is not None:
            autosave(self.doc)

    # -- image import ---------------------------------------------------

    def _import_image(self) -> None:
        if self.doc is None:
            QMessageBox.information(self, "No Project", "Create or open a project first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import Image", "", IMAGE_FILE_FILTER)
        if not path:
            return
        from ..project_io import load_image_rgba

        try:
            image = load_image_rgba(path)
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", str(exc))
            return

        layer_id = new_id("layer")
        layer = Layer(id=layer_id, name=Path(path).stem, image_filename=f"{layer_id}.png")
        self.doc.set_layer_image(layer_id, image)
        self.doc.project.add_layer(layer)

        self._refresh_all()
        self._autosave()

    # -- layer panel handlers --------------------------------------------

    def _on_layer_selected(self, layer_id: str) -> None:
        if self.doc is None:
            return
        self.doc.project.active_layer_id = layer_id
        layer = self.doc.project.get_layer(layer_id)
        if layer is not None:
            self.transform_panel.set_transform(layer.transform)
        self.layers_panel.sync_appearance(layer)

    def _on_layer_visibility_toggled(self, layer_id: str, visible: bool) -> None:
        layer = self._get_layer(layer_id)
        if layer:
            layer.visible = visible
            self._autosave()
            self._rerender()

    def _on_layer_opacity_changed(self, layer_id: str, opacity: float) -> None:
        layer = self._get_layer(layer_id)
        if layer:
            layer.opacity = opacity
            self._autosave()
            self._rerender()

    def _on_layer_blend_mode_changed(self, layer_id: str, mode_value: str) -> None:
        layer = self._get_layer(layer_id)
        if layer:
            layer.blend_mode = BlendMode(mode_value)
            self._autosave()
            self._rerender()

    def _on_delete_layer(self, layer_id: str) -> None:
        if self.doc is None:
            return
        self.doc.project.remove_layer(layer_id)
        self.doc.images.pop(layer_id, None)
        self._refresh_all()
        self._autosave()

    def _on_move_layer(self, layer_id: str, direction: int) -> None:
        if self.doc is None:
            return
        layers = self.doc.project.layers
        idx = next((i for i, l in enumerate(layers) if l.id == layer_id), None)
        if idx is None:
            return
        self.doc.project.move_layer(layer_id, idx + direction)
        self._refresh_all()
        self._autosave()

    def _on_rename_layer(self, layer_id: str, new_name: str) -> None:
        layer = self._get_layer(layer_id)
        if layer:
            layer.name = new_name
            self._refresh_all()
            self._autosave()

    def _on_perspective_correct(self, layer_id: str) -> None:
        if self.doc is None:
            return
        layer = self._get_layer(layer_id)
        raw_image = self.doc.get_layer_image(layer_id)
        if layer is None or raw_image is None:
            return
        dialog = PerspectiveDialog(raw_image, layer.perspective_corners, self)
        if dialog.exec() == PerspectiveDialog.Accepted:
            layer.perspective_corners = dialog.result_corners()
            self._autosave()
            self._rerender()

    # -- transform / grid / compare handlers -----------------------------

    def _on_transform_changed(self, transform: Transform) -> None:
        if self.doc is None or self.doc.project.active_layer_id is None:
            return
        layer = self._get_layer(self.doc.project.active_layer_id)
        if layer:
            layer.transform = transform
            self._autosave()
            self._rerender()

    def _on_canvas_drag(self, dx: float, dy: float) -> None:
        if self.doc is None or self.doc.project.active_layer_id is None:
            return
        self.transform_panel.nudge_offset(dx, dy)

    def _on_grid_changed(self, grid) -> None:
        if self.doc is None:
            return
        self.doc.project.grid = grid
        self._autosave()
        self._rerender()

    def _on_compare_changed(self) -> None:
        if self.doc is None:
            return
        project = self.doc.project
        project.compare_mode = self.compare_panel.current_mode()
        project.compare_layer_a = self.compare_panel.current_layer_a_id()
        project.compare_layer_b = self.compare_panel.current_layer_b_id()
        project.split_position = self.compare_panel.current_split_position()

        if project.compare_mode == CompareMode.BLINK:
            self.blink_timer.setInterval(self.compare_panel.current_blink_interval_ms())
            if not self.blink_timer.isActive():
                self._blink_showing_a = True
                self.blink_timer.start()
        else:
            self.blink_timer.stop()

        self._autosave()
        self._rerender()

    def _on_blink_tick(self) -> None:
        self._blink_showing_a = not self._blink_showing_a
        self._rerender()

    # -- helpers ----------------------------------------------------------

    def _get_layer(self, layer_id: str) -> Layer | None:
        return self.doc.project.get_layer(layer_id) if self.doc else None

    def _refresh_all(self) -> None:
        self._update_enabled_state()
        if self.doc is None:
            return
        project = self.doc.project
        self.layers_panel.refresh(project)
        active = project.get_layer(project.active_layer_id) if project.active_layer_id else None
        self.transform_panel.set_transform(active.transform if active else Transform())
        self.transform_panel.setEnabled(active is not None)
        self.grid_panel.set_grid(project.grid)
        self.compare_panel.refresh_layers(project)
        self._rerender()

    def _rerender(self) -> None:
        if self.doc is None:
            return
        project = self.doc.project
        canvas_size = compute_canvas_pixel_size(project)
        mode = project.compare_mode

        if mode == CompareMode.BLINK and project.compare_layer_a and project.compare_layer_b:
            layer_id = project.compare_layer_a if self._blink_showing_a else project.compare_layer_b
            composite = self._render_single_layer(layer_id, canvas_size)
        elif mode == CompareMode.SPLIT and project.compare_layer_a and project.compare_layer_b:
            img_a = self._render_single_layer(project.compare_layer_a, canvas_size)
            img_b = self._render_single_layer(project.compare_layer_b, canvas_size)
            composite = split_view(img_a, img_b, project.split_position)
        else:
            composite = render_composite(self.doc, canvas_size)

        self.canvas_view.set_image(rgba_float_to_qpixmap(composite))

    def _render_single_layer(self, layer_id: str | None, canvas_size):
        plane = render_layer(self.doc, layer_id, canvas_size) if layer_id else None
        if plane is None:
            return blank_canvas(canvas_size)
        return composite_layers([(plane, 1.0, BlendMode.NORMAL)], canvas_size)
