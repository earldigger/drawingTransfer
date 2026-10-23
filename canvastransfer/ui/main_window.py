from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import color_study
from ..compare import display_states, uses_split_line
from ..geometry import (
    TransformMode,
    canvas_pixel_size,
    canvas_quad,
    denormalize_quad,
    fit_quad,
    flip_horizontal,
    flip_vertical,
    normalize_quad,
)
from ..history import History, Snapshot
from ..models import BlendMode, CompareMode, Layer, Project, Swatch, new_id
from ..paints import PaintLibrary
from ..project_io import ProjectDocument, autosave, load_image_rgba, load_project, save_project
from .canvas_view import CanvasView, LayerEntry, Marker
from .color_panel import ColorStudyPanel
from .compare_panel import ComparePanel
from .grid_panel import GridPanel
from .layer_display import LayerDisplayCache
from .layers_panel import LayersPanel
from .library_location import library_path
from .paint_library import PaintLibraryDialog
from .paint_panel import PaintMatchPanel
from .new_project_dialog import NewProjectDialog
from .perspective_dialog import PerspectiveDialog
from .projects_folder import choose_projects_folder, new_project_path, projects_folder, set_projects_folder
from .recent_projects import THUMBNAIL_FILE, add_recent, recent_projects, remove_recent
from .start_screen import StartScreen

IMAGE_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
AUTOSAVE_DELAY_MS = 500
THUMBNAIL_INTERVAL_S = 10  # autosave refreshes the project's thumbnail at most this often

MODE_LABELS = [
    (TransformMode.UNIFORM, "Proportional", "Corner and edge handles scale evenly, keeping proportions"),
    (TransformMode.FREE, "Free", "Handles stretch width and height independently"),
    (TransformMode.SKEW, "Skew", "Edge handles slide an edge sideways (shear); corners scale freely"),
    (TransformMode.DISTORT, "Distort", "Each corner moves on its own"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Canvas Transfer (prototype)")
        self.resize(1400, 900)

        self.doc: ProjectDocument | None = None
        self.cache = LayerDisplayCache()
        self.history = History()
        self._canvas_size = (1, 1)
        self._mode = TransformMode.UNIFORM
        self._selected_swatch_id: str | None = None

        self._blink_on = True
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._on_blink_tick)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(AUTOSAVE_DELAY_MS)
        self._autosave_timer.timeout.connect(self._autosave_now)

        self.canvas_view = CanvasView()
        self.start_screen = StartScreen()
        self.start_screen.newRequested.connect(self._new_project)
        self.start_screen.openRequested.connect(self._open_project)
        self.start_screen.recentChosen.connect(self._open_recent)
        self.start_screen.folderChangeRequested.connect(self.change_projects_folder)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.start_screen)
        self.stack.addWidget(self.canvas_view)
        self.setCentralWidget(self.stack)
        self._thumbnail_time = 0.0
        self._on_start_screen = False
        self.canvas_view.quadCommitted.connect(self._on_quad_committed)
        self.canvas_view.colorPicked.connect(self._on_color_picked)
        self.canvas_view.pickHover.connect(self._on_pick_hover)
        self.canvas_view.markerClicked.connect(self._select_swatch)

        self.layers_panel = LayersPanel()
        self.grid_panel = GridPanel()
        self.compare_panel = ComparePanel()
        self.color_panel = ColorStudyPanel()
        self.paint_library = self._load_paint_library()
        self.paint_panel = PaintMatchPanel(self.paint_library)
        self.library_dialog: PaintLibraryDialog | None = None
        self._build_side_dock()
        self._build_menu()
        self._build_toolbar()
        self._wire_panels()

        self.statusBar().showMessage("Create or open a project to begin.")
        self._update_enabled_state()
        QApplication.instance().applicationStateChanged.connect(self._on_app_state_changed)

    # -- layout -------------------------------------------------------

    def _build_side_dock(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        for panel in (self.layers_panel, self.grid_panel, self.compare_panel):
            layout.addWidget(panel)
        layout.addStretch(1)

        self.side_tabs = QTabWidget()
        for widget, title in ((container, "Workspace"), (self.color_panel, "Color Study"),
                              (self.paint_panel, "Paints")):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            scroll.setMinimumWidth(380)
            self.side_tabs.addTab(scroll, title)

        dock = QDockWidget("Panels", self)
        dock.setWidget(self.side_tabs)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.side_dock = dock

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("New Project…", QKeySequence.New, self._new_project)
        file_menu.addAction("Open Project…", QKeySequence.Open, self._open_project)
        self.recent_menu = file_menu.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        file_menu.addSeparator()
        self.close_action = file_menu.addAction("Close Project", QKeySequence.Close, self.close_project)
        self.close_action.setToolTip("Close the project and go back to the start screen")
        self.save_action = file_menu.addAction("Save", QKeySequence.Save, self._save_project)
        self.save_as_action = file_menu.addAction("Save As…", QKeySequence.SaveAs, self._save_project_as)
        file_menu.addSeparator()
        file_menu.addAction("Projects Folder…", self.change_projects_folder)
        file_menu.addSeparator()
        self.add_layer_action = file_menu.addAction("Add Image Layer…", self._import_image)

        edit_menu = self.menuBar().addMenu("&Edit")
        self.undo_action = edit_menu.addAction("Undo", QKeySequence.Undo, self._undo)
        self.redo_action = edit_menu.addAction("Redo", QKeySequence.Redo, self._redo)

        color_menu = self.menuBar().addMenu("&Color")
        self.paint_library_action = color_menu.addAction("Paint Library…", self.open_paint_library)
        color_menu.addAction("Palettes…", lambda: self.open_paint_library(palettes=True))
        color_menu.addSeparator()
        color_menu.addAction("Paint Library Location…", self.change_library_location)

    def _build_toolbar(self) -> None:
        bar = QToolBar("Transform", self)
        bar.setMovable(False)
        self.tool_bar = bar
        bar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(Qt.TopToolBarArea, bar)

        bar.addAction(self.undo_action)
        bar.addAction(self.redo_action)
        bar.addSeparator()

        self.transform_action = QAction("Transform", self)
        self.transform_action.setCheckable(True)
        self.transform_action.setShortcut("T")
        self.transform_action.setToolTip("Show the transform box on the selected layer (T)")
        self.transform_action.toggled.connect(self._on_tool_toggled)
        bar.addAction(self.transform_action)

        self.done_action = bar.addAction("Done", lambda: self._end_session(commit=True))
        self.done_action.setShortcuts([QKeySequence(Qt.Key_Return), QKeySequence(Qt.Key_Enter)])
        self.done_action.setToolTip("Keep the transform (Return)")
        self.cancel_action = bar.addAction("Cancel", lambda: self._end_session(commit=False))
        self.cancel_action.setShortcut(QKeySequence(Qt.Key_Escape))
        self.cancel_action.setToolTip("Undo everything since Transform was turned on (Esc)")
        bar.addSeparator()

        self.pick_action = QAction("Pick Color", self)
        self.pick_action.setCheckable(True)
        self.pick_action.setShortcut("I")
        self.pick_action.setToolTip("Click the selected layer to add a color swatch (I)")
        self.pick_action.toggled.connect(self._on_pick_toggled)
        bar.addAction(self.pick_action)
        bar.addSeparator()

        group = QActionGroup(self)
        group.setExclusive(True)
        self.mode_actions: dict[TransformMode, QAction] = {}
        for mode, label, tip in MODE_LABELS:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setToolTip(tip)
            action.triggered.connect(lambda _checked, m=mode: self._on_mode_chosen(m))
            group.addAction(action)
            bar.addAction(action)
            self.mode_actions[mode] = action
        self.mode_actions[self._mode].setChecked(True)
        bar.addSeparator()

        self.flip_h_action = bar.addAction("Flip Horizontal", lambda: self._flip(horizontal=True))
        self.flip_v_action = bar.addAction("Flip Vertical", lambda: self._flip(horizontal=False))
        self.fit_action = bar.addAction("Fit to Canvas", self._fit_active)
        self.fit_action.setToolTip("Reset the selected layer to fit inside the canvas")

    def _wire_panels(self) -> None:
        lp = self.layers_panel
        lp.layerSelected.connect(self._on_layer_selected)
        lp.layerVisibilityToggled.connect(lambda lid, v: self._set_layer_attr(lid, "visible", v))
        lp.layerOpacityChanged.connect(lambda lid, v: self._set_layer_attr(lid, "opacity", v, key=("opacity", lid)))
        lp.layerBlendModeChanged.connect(lambda lid, v: self._set_layer_attr(lid, "blend_mode", BlendMode(v)))
        lp.layerAdjustmentsChanged.connect(
            lambda lid, adj, slider: self._set_layer_attr(
                lid, "adjustments", adj, key=("adjust", slider, lid) if slider else None
            )
        )
        lp.addLayerRequested.connect(self._import_image)
        lp.deleteLayerRequested.connect(self._on_delete_layer)
        lp.moveLayerUpRequested.connect(lambda lid: self._on_move_layer(lid, +1))
        lp.moveLayerDownRequested.connect(lambda lid: self._on_move_layer(lid, -1))
        lp.renameLayerRequested.connect(self._on_rename_layer)
        lp.perspectiveCorrectRequested.connect(self._on_perspective_correct)

        self.grid_panel.gridChanged.connect(self._on_grid_changed)
        self.compare_panel.settingsChanged.connect(self._on_compare_changed)

        cp = self.color_panel
        cp.swatchSelected.connect(self._select_swatch)
        cp.swatchRemoveRequested.connect(self._on_remove_swatch)
        cp.swatchHighlightToggled.connect(self._on_swatch_highlight)
        cp.toleranceChanged.connect(self._on_tolerance_changed)
        cp.sampleSizeChanged.connect(lambda _: self._update_pick_cursor())
        cp.simplifyChanged.connect(self._on_simplify_changed)
        cp.addSimplifiedSwatchesRequested.connect(self._add_simplified_swatches)
        self.paint_panel.openLibraryRequested.connect(self.open_paint_library)
        self.paint_panel.openPalettesRequested.connect(lambda: self.open_paint_library(palettes=True))

    def _update_enabled_state(self) -> None:
        has_project = self.doc is not None
        has_layer = has_project and self._active_layer() is not None
        self.layers_panel.setEnabled(has_project)
        self.grid_panel.setEnabled(has_project)
        self.compare_panel.setEnabled(has_project)
        self.color_panel.setEnabled(has_project)
        for action in (self.close_action, self.save_action, self.save_as_action, self.add_layer_action):
            action.setEnabled(has_project)
        # no project: the start screen, without the editing toolbar and panels
        self.stack.setCurrentWidget(self.canvas_view if has_project else self.start_screen)
        self.tool_bar.setVisible(has_project)
        self.side_dock.setVisible(has_project)
        if not has_project and not self._on_start_screen:
            self.start_screen.refresh()  # recents may have changed while a project was open
        self._on_start_screen = not has_project
        for action in [self.transform_action, self.flip_h_action, self.flip_v_action, self.fit_action,
                       self.pick_action, *self.mode_actions.values()]:
            action.setEnabled(has_layer)
        self._update_history_actions()

    def _update_history_actions(self) -> None:
        self.undo_action.setEnabled(self.doc is not None and self.history.can_undo())
        self.redo_action.setEnabled(self.doc is not None and self.history.can_redo())
        self.done_action.setEnabled(self.history.in_session)
        self.cancel_action.setEnabled(self.history.in_session)

    # -- project lifecycle ---------------------------------------------

    def _set_document(self, doc: ProjectDocument) -> None:
        self._flush_autosave()
        self._write_thumbnail(force=True)
        self.history.clear()
        self._set_tool_checked(False)
        self.pick_action.setChecked(False)
        self._selected_swatch_id = None
        self.doc = doc
        self.cache.clear()
        self._blink_on = True
        self.blink_timer.stop()
        self._canvas_size = canvas_pixel_size(doc.project.canvas_width, doc.project.canvas_height)
        self.canvas_view.set_canvas_size(*self._canvas_size)
        self._refresh_all()
        self._restart_blink_if_needed()

    def _new_project(self) -> None:
        if not self._confirm_leave():
            return
        dialog = NewProjectDialog(self)
        if dialog.exec() != NewProjectDialog.Accepted:
            return
        name, width, height, units = dialog.values()
        self.create_project(Project(name=name, canvas_width=width, canvas_height=height, units=units))

    def create_project(self, project: Project) -> None:
        """Open a new project, saved straight away in the projects folder so
        it autosaves and shows on the start screen."""
        self._set_document(ProjectDocument(project))
        path = new_project_path(project.name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            save_project(self.doc, path)
        except OSError as e:
            QMessageBox.warning(self, "New Project", f"Couldn't save the project in {path.parent} ({e}).\n"
                                "It is open but not saved; use File > Save As, or choose another projects folder.")
            return
        add_recent(path, project.name)
        self.statusBar().showMessage(f"New project '{project.name}' saved in {path.parent}; changes autosave.")

    def _open_project(self) -> None:
        if not self._confirm_leave():
            return
        folder = projects_folder()
        path = QFileDialog.getExistingDirectory(self, "Open Project (.ctproj folder)",
                                                str(folder if folder.is_dir() else Path.home()))
        if path:
            self.open_project_path(path)

    def _open_recent(self, path: str) -> None:
        if self.doc is not None and self.doc.package_dir is not None and \
                Path(path).resolve() == Path(self.doc.package_dir).resolve():
            return  # already open
        if not self._confirm_leave():
            return
        if not self.open_project_path(path):
            if QMessageBox.question(self, "Open Recent", "Remove it from the recent projects?") == QMessageBox.Yes:
                remove_recent(path)
                self.start_screen.refresh()

    def open_project_path(self, path: str | Path) -> bool:
        try:
            doc = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open Project Failed", f"Couldn't open {path}:\n{exc}")
            return False
        self._set_document(doc)
        add_recent(doc.package_dir, doc.project.name)
        self.statusBar().showMessage(f"Opened '{doc.project.name}' from {path}")
        return True

    def change_projects_folder(self) -> None:
        folder = choose_projects_folder(self)
        if folder is None:
            return
        set_projects_folder(folder)
        self.start_screen.refresh()
        self.statusBar().showMessage(f"New projects will be saved in {folder}")

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        recents = recent_projects()
        for r in recents:
            self.recent_menu.addAction(r.name, lambda p=str(r.path): self._open_recent(p)).setToolTip(str(r.path))
        if not recents:
            self.recent_menu.addAction("No recent projects").setEnabled(False)

    def close_project(self) -> bool:
        """Back to the start screen. False if the user cancelled."""
        if self.doc is None:
            return True
        if not self._confirm_leave():
            return False
        self._flush_autosave()
        self._write_thumbnail(force=True)
        self.history.clear()
        self._set_tool_checked(False)
        self.pick_action.setChecked(False)
        self._selected_swatch_id = None
        self.doc = None
        self.cache.clear()
        self.blink_timer.stop()
        self.canvas_view.show_layers([], None)
        self._update_paint_target()
        self._update_enabled_state()
        self.statusBar().showMessage("Create or open a project to begin.")
        return True

    def _confirm_leave(self) -> bool:
        """Before closing the current project: a project that was never
        saved but has layers would be lost, so offer to save it."""
        doc = self.doc
        if doc is None or doc.package_dir is not None or not doc.project.layers:
            return True
        choice = self._ask_save_unsaved(doc.project.name)
        if choice == "save":
            self._save_project_as()
            return self.doc.package_dir is not None
        return choice == "discard"

    def _ask_save_unsaved(self, name: str) -> str | None:
        """'save', 'discard' or None (cancel)."""
        answer = QMessageBox.question(
            self, "Unsaved Project", f"“{name}” has never been saved. Save it before closing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        return {QMessageBox.Save: "save", QMessageBox.Discard: "discard"}.get(answer)

    def _write_thumbnail(self, force: bool = False) -> None:
        """Save a small picture of the canvas in the project, for the start screen."""
        doc = self.doc
        if doc is None or doc.package_dir is None or not doc.project.layers:
            return
        if not force and time.monotonic() - self._thumbnail_time < THUMBNAIL_INTERVAL_S:
            return
        self._thumbnail_time = time.monotonic()
        self.canvas_view.render_thumbnail().save(str(Path(doc.package_dir) / THUMBNAIL_FILE))

    def _save_project(self) -> None:
        if self.doc is None:
            return
        if self.doc.package_dir is None:
            self._save_project_as()
            return
        save_project(self.doc, self.doc.package_dir)
        self._write_thumbnail(force=True)
        add_recent(self.doc.package_dir, self.doc.project.name)
        self.statusBar().showMessage(f"Saved to {self.doc.package_dir}")

    def _save_project_as(self) -> None:
        if self.doc is None:
            return
        suggested = f"{self.doc.project.name}.ctproj"
        path, _ = QFileDialog.getSaveFileName(self, "Save Project As", suggested, "Canvas Transfer Project (*.ctproj)")
        if not path:
            return
        save_project(self.doc, path)
        self._write_thumbnail(force=True)
        add_recent(self.doc.package_dir, self.doc.project.name)
        self.statusBar().showMessage(f"Saved to {path} -- changes now autosave.")

    def _schedule_autosave(self) -> None:
        if self.doc is not None and self.doc.package_dir is not None:
            self._autosave_timer.start()

    def _autosave_now(self) -> None:
        if self.doc is not None and autosave(self.doc):
            self._write_thumbnail()

    def _flush_autosave(self) -> None:
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
            self._autosave_now()

    def closeEvent(self, event):
        if not self._confirm_leave():
            event.ignore()
            return
        self._flush_autosave()
        self._write_thumbnail(force=True)
        super().closeEvent(event)

    # -- undo / redo / transform sessions ---------------------------------

    def _snapshot(self) -> Snapshot:
        return Snapshot(self.doc.project.to_dict(), dict(self.doc.images))

    def _record(self, key=None, transform: bool = False) -> None:
        """Call before every project change. A non-transform change ends
        any open transform session first, so Cancel only ever reverts
        transforms."""
        if self.history.in_session and not transform:
            self._end_session(commit=True)
        self.history.record(self._snapshot(), key)
        self._update_history_actions()

    def _restore(self, snap: Snapshot) -> None:
        current = self.doc.project
        project = Project.from_dict(snap.project)
        # Compare settings are a viewing choice, not an edit: keep them.
        project.compare_mode = current.compare_mode
        project.compare_layer_a = current.compare_layer_a
        project.compare_layer_b = current.compare_layer_b
        project.split_position = current.split_position
        project.simplify = current.simplify  # a way of looking, not an edit
        if project.get_layer(current.active_layer_id) is not None:
            project.active_layer_id = current.active_layer_id
        self.doc.project = project
        self.doc.images = dict(snap.images)
        self._refresh_all()
        self._restart_blink_if_needed()
        self._schedule_autosave()

    def _undo(self) -> None:
        if self.doc is None:
            return
        snap = self.history.undo(self._snapshot())
        if snap is not None:
            self._restore(snap)
        self._update_history_actions()

    def _redo(self) -> None:
        if self.doc is None:
            return
        snap = self.history.redo(self._snapshot())
        if snap is not None:
            self._restore(snap)
        self._update_history_actions()

    def _set_tool_checked(self, checked: bool) -> None:
        self.transform_action.blockSignals(True)
        self.transform_action.setChecked(checked)
        self.transform_action.blockSignals(False)
        self.canvas_view.set_tool(checked, self._mode)

    def _end_session(self, commit: bool) -> None:
        if not self.history.in_session:
            return
        if commit:
            self.history.commit_session()
            self.statusBar().showMessage("Transform applied. Undo (⌘Z) reverts it in one step.")
        else:
            start = self.history.cancel_session()
            if start is not None:
                self._restore(start)
            self.statusBar().showMessage("Transform cancelled.")
        self._set_tool_checked(False)
        self._update_history_actions()

    # -- image import -----------------------------------------------------

    def _import_image(self) -> None:
        if self.doc is None:
            QMessageBox.information(self, "No Project", "Create or open a project first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import Image", "", IMAGE_FILE_FILTER)
        if not path:
            return
        try:
            image = load_image_rgba(path)
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", f"{exc}\n\nHEIC photos aren't supported yet -- export as JPEG first.")
            return

        self._record()
        layer_id = new_id("layer")
        layer = Layer(id=layer_id, name=Path(path).stem, image_filename=f"{layer_id}.png")
        self.doc.set_layer_image(layer_id, image)
        self.doc.project.add_layer(layer)
        self._refresh_all()
        self.transform_action.setChecked(True)
        self.statusBar().showMessage(
            "Image fitted to the canvas. Drag inside the box to move, drag handles to scale, "
            "drag the blue dot to rotate. Return = Done, Esc = Cancel."
        )
        self._schedule_autosave()

    # -- layer handlers ------------------------------------------------------

    def _active_layer(self) -> Layer | None:
        return self.doc.project.get_layer(self.doc.project.active_layer_id) if self.doc else None

    def _on_layer_selected(self, layer_id: str) -> None:
        if self.doc is None:
            return
        if self.history.in_session and layer_id != self.doc.project.active_layer_id:
            # Finish the transform on the old layer; keep transforming the new one.
            self.history.commit_session()
            self.history.begin_session()
        self.doc.project.active_layer_id = layer_id
        self.layers_panel.sync_appearance(self._active_layer())
        self.canvas_view.set_active_layer(layer_id)
        if self.doc.project.simplify.enabled:
            self._refresh_canvas()  # Simplify follows the selected layer
        self._update_enabled_state()
        if self.pick_action.isChecked():
            self._update_pick_cursor()

    def _set_layer_attr(self, layer_id: str, attr: str, value, key=None) -> None:
        layer = self.doc.project.get_layer(layer_id) if self.doc else None
        if layer is None or getattr(layer, attr) == value:
            return
        self._record(key)
        setattr(layer, attr, value)
        self._refresh_canvas()
        self._schedule_autosave()

    def _on_delete_layer(self, layer_id: str) -> None:
        if self.doc is None:
            return
        self._record()
        self.doc.project.remove_layer(layer_id)
        self.doc.images.pop(layer_id, None)
        self.cache.forget(layer_id)
        self._refresh_all()
        self._schedule_autosave()

    def _on_move_layer(self, layer_id: str, direction: int) -> None:
        if self.doc is None:
            return
        idx = next((i for i, l in enumerate(self.doc.project.layers) if l.id == layer_id), None)
        if idx is None or not 0 <= idx + direction < len(self.doc.project.layers):
            return
        self._record()
        self.doc.project.move_layer(layer_id, idx + direction)
        self._refresh_all()
        self._schedule_autosave()

    def _on_rename_layer(self, layer_id: str, new_name: str) -> None:
        layer = self.doc.project.get_layer(layer_id) if self.doc else None
        if layer and layer.name != new_name:
            self._record()
            layer.name = new_name
            self._refresh_all()
            self._schedule_autosave()

    def _on_perspective_correct(self, layer_id: str) -> None:
        layer = self.doc.project.get_layer(layer_id) if self.doc else None
        raw = self.doc.get_layer_image(layer_id) if self.doc else None
        if layer is None or raw is None:
            return
        dialog = PerspectiveDialog(raw, layer.perspective_corners, layer.perspective_fill_canvas, self)
        if dialog.exec() == PerspectiveDialog.Accepted:
            self._record()
            layer.perspective_corners = dialog.result_corners()
            layer.perspective_fill_canvas = dialog.result_fill_canvas()
            layer.quad = None  # re-place the corrected image
            self._refresh_canvas()
            self._schedule_autosave()

    # -- transform tool ---------------------------------------------------------

    def _on_tool_toggled(self, enabled: bool) -> None:
        """Turning Transform on starts a session; turning it off is Done."""
        if enabled and self.pick_action.isChecked():
            self.pick_action.setChecked(False)
        if enabled:
            self.history.begin_session()
            self.canvas_view.set_tool(True, self._mode)
            self._update_history_actions()
        else:
            self._end_session(commit=True)

    def _on_mode_chosen(self, mode: TransformMode) -> None:
        self._mode = mode
        if not self.transform_action.isChecked():
            self.transform_action.setChecked(True)
        self.canvas_view.set_tool(True, mode)

    def _on_quad_committed(self, layer_id: str, quad) -> None:
        layer = self.doc.project.get_layer(layer_id) if self.doc else None
        if layer is not None:
            self._record(transform=True)
            layer.quad = normalize_quad(quad, *self._canvas_size)
            self._schedule_autosave()

    def _flip(self, horizontal: bool) -> None:
        layer = self._active_layer()
        if layer is None or layer.quad is None:
            return
        self._record(transform=True)
        quad = denormalize_quad(layer.quad, *self._canvas_size)
        quad = flip_horizontal(quad) if horizontal else flip_vertical(quad)
        layer.quad = normalize_quad(quad, *self._canvas_size)
        self._refresh_canvas()
        self._schedule_autosave()

    def _fit_active(self) -> None:
        layer = self._active_layer()
        if layer is None:
            return
        self._record(transform=True)
        layer.quad = None
        self._refresh_canvas()
        self.canvas_view.refit()
        self._schedule_autosave()

    def _placement(self, layer: Layer, pixmap) -> list:
        cw, ch = self._canvas_size
        if layer.quad is None:
            if layer.perspective_corners is not None and layer.perspective_fill_canvas:
                quad = canvas_quad(cw, ch)
            else:
                quad = fit_quad(pixmap.width(), pixmap.height(), cw, ch)
            layer.quad = normalize_quad(quad, cw, ch)
            self._schedule_autosave()
        return denormalize_quad(layer.quad, cw, ch)

    # -- grid / compare -----------------------------------------------------------

    def _on_grid_changed(self, grid) -> None:
        if self.doc is None or grid == self.doc.project.grid:
            return
        self._record(key=("grid",))
        self.doc.project.grid = grid
        self.canvas_view.set_grid(grid)
        self._schedule_autosave()

    def _on_compare_changed(self) -> None:
        if self.doc is None:
            return
        project = self.doc.project
        project.compare_mode = self.compare_panel.current_mode()
        project.compare_layer_a = self.compare_panel.current_layer_a_id()
        project.compare_layer_b = self.compare_panel.current_layer_b_id()
        project.split_position = self.compare_panel.current_split_position()
        self._restart_blink_if_needed()
        self._refresh_canvas()
        self._schedule_autosave()

    def _restart_blink_if_needed(self) -> None:
        blinking = self.doc is not None and self.doc.project.compare_mode in (CompareMode.BLINK, CompareMode.BLINK_A)
        if blinking:
            self.blink_timer.setInterval(self.compare_panel.current_blink_interval_ms())
            if not self.blink_timer.isActive():
                self._blink_on = True
                self.blink_timer.start()
        else:
            self.blink_timer.stop()
            self._blink_on = True

    def _on_blink_tick(self) -> None:
        self._blink_on = not self._blink_on
        self._refresh_canvas()

    # -- refresh --------------------------------------------------------------------

    def _refresh_all(self) -> None:
        self._update_enabled_state()
        if self.doc is None:
            return
        project = self.doc.project
        self.layers_panel.refresh(project)
        self.grid_panel.set_grid(project.grid)
        self.compare_panel.refresh_layers(project)
        if project.get_swatch(self._selected_swatch_id) is None:
            self._selected_swatch_id = None
        self.color_panel.refresh(project, self._selected_swatch_id)
        self.color_panel.set_simplify(project.simplify)
        self._update_paint_target()
        if self.compare_panel.current_layer_a_id() != project.compare_layer_a or \
                self.compare_panel.current_layer_b_id() != project.compare_layer_b:
            project.compare_layer_a = self.compare_panel.current_layer_a_id()
            project.compare_layer_b = self.compare_panel.current_layer_b_id()
        self._refresh_canvas()

    def _refresh_canvas(self) -> None:
        if self.doc is None:
            return
        project = self.doc.project
        states = display_states(project, self._blink_on)
        entries = []
        for layer in project.layers:
            pixmap = self.cache.pixmap(self.doc, layer, self._canvas_size)
            if pixmap is None:
                continue
            entries.append(LayerEntry(layer.id, pixmap, self._placement(layer, pixmap), states[layer.id]))
        split = project.split_position if uses_split_line(project) else None
        self.canvas_view.show_layers(entries, split, self._highlight_overlays())
        self._update_markers()
        if self.pick_action.isChecked():
            self._update_pick_cursor()
        self.canvas_view.set_grid(project.grid)
        self.canvas_view.set_active_layer(project.active_layer_id)
        self._show_simplified_palette()

    # -- color study ------------------------------------------------------------------

    def _on_pick_toggled(self, enabled: bool) -> None:
        if enabled and self.history.in_session:
            self._end_session(commit=True)
        if enabled:
            self._show_color_tab()
            self.statusBar().showMessage("Click the selected layer to add a swatch. Press I to stop picking.")
        else:
            self.color_panel.show_hover(None)
        self._update_pick_cursor()

    def _update_pick_cursor(self) -> None:
        """Size the cursor ring to the sample area, in canvas units."""
        radius = 0.0
        layer = self._active_layer()
        entry = self.canvas_view.entry(layer.id) if layer else None
        quad = self.canvas_view.quad(layer.id) if layer else None
        if entry is not None and quad is not None:
            width_on_canvas = ((quad[1][0] - quad[0][0]) ** 2 + (quad[1][1] - quad[0][1]) ** 2) ** 0.5
            radius = (self.color_panel.sample_radius() + 0.5) * width_on_canvas / entry.pixmap.width()
        self.canvas_view.set_pick(self.pick_action.isChecked(), radius)

    def _sample_at(self, x: float, y: float):
        """(layer, u, v, rgb) for a scene point on the selected layer, or None."""
        layer = self._active_layer()
        if layer is None:
            return None
        image = self.cache.adjusted_image(self.doc, layer, self._canvas_size)
        point = self.canvas_view.layer_point(layer.id, x, y)
        if image is None or point is None:
            return None
        h, w = image.shape[:2]
        simplified = self._simplified(layer)
        if simplified is not None:  # pick what the canvas shows: one flat color
            flat = simplified[0].image
            sh, sw = flat.shape[:2]
            rgb = color_study.sample_average(flat, point[0] * sw / w, point[1] * sh / h, 0)
        else:
            rgb = color_study.sample_average(image, point[0], point[1], self.color_panel.sample_radius())
        if rgb is None:
            return None
        return layer, point[0] / w, point[1] / h, rgb

    def _on_pick_hover(self, point) -> None:
        sample = self._sample_at(*point) if point is not None and self.doc else None
        self.color_panel.show_hover(sample[3] if sample else None)

    def _on_color_picked(self, x: float, y: float) -> None:
        if self.doc is None:
            return
        sample = self._sample_at(x, y)
        if sample is None:
            self.statusBar().showMessage("Click inside the selected layer to pick a color.")
            return
        layer, u, v, rgb = sample
        self._record()
        swatch = Swatch(id=new_id("swatch"), layer_id=layer.id, u=u, v=v, rgb=rgb)
        self.doc.project.swatches.append(swatch)
        self._selected_swatch_id = swatch.id
        self._refresh_color_study()
        self.statusBar().showMessage(f"Added swatch {len(self.doc.project.swatches)}: {color_study.hex_code(rgb)}")
        self._schedule_autosave()

    def _select_swatch(self, swatch_id: str) -> None:
        if self.doc is None or self.doc.project.get_swatch(swatch_id) is None:
            return
        self._selected_swatch_id = swatch_id
        self._show_color_tab()
        self.color_panel.refresh(self.doc.project, swatch_id)
        self._update_paint_target()
        self._update_markers()

    def _on_remove_swatch(self, swatch_id: str) -> None:
        swatches = self.doc.project.swatches if self.doc else []
        index = next((i for i, s in enumerate(swatches) if s.id == swatch_id), None)
        if index is None:
            return
        self._record()
        swatches.pop(index)
        neighbor = swatches[min(index, len(swatches) - 1)] if swatches else None
        self._selected_swatch_id = neighbor.id if neighbor else None
        self._refresh_color_study()
        self._schedule_autosave()

    def _on_swatch_highlight(self, swatch_id: str, on: bool) -> None:
        swatch = self.doc.project.get_swatch(swatch_id) if self.doc else None
        if swatch is None or swatch.highlight == on:
            return
        self._record()
        swatch.highlight = on
        self._refresh_color_study()
        self._schedule_autosave()

    def _on_tolerance_changed(self, tolerance: float) -> None:
        if self.doc is None or tolerance == self.doc.project.highlight_tolerance:
            return
        self._record(key=("tolerance",))
        self.doc.project.highlight_tolerance = tolerance
        self._refresh_canvas()
        self._schedule_autosave()

    def _refresh_color_study(self) -> None:
        self.color_panel.refresh(self.doc.project, self._selected_swatch_id)
        self._update_paint_target()
        self._refresh_canvas()

    def _show_color_tab(self) -> None:
        """Bring Color Study forward, unless Paints (which also follows the
        selected swatch) is already showing."""
        if self.side_tabs.currentWidget().widget() is not self.paint_panel:
            self.side_tabs.setCurrentIndex(1)

    # -- paints -------------------------------------------------------------------

    def _load_paint_library(self) -> PaintLibrary:
        path = library_path()
        try:
            return PaintLibrary.load(path)
        except (OSError, ValueError, TypeError, KeyError) as e:
            damaged = path.with_name(path.stem + ".damaged.json")
            try:
                path.replace(damaged)
            except OSError:
                pass
            QMessageBox.warning(self, "Paint Library", f"Couldn't read the paint library ({e}). "
                                f"It was set aside as {damaged.name}; starting with an empty library.")
            return PaintLibrary(path=path)

    def open_paint_library(self, palettes: bool = False) -> None:
        if self.library_dialog is None:
            self.library_dialog = PaintLibraryDialog(self.paint_library, self)
            self.library_dialog.libraryChanged.connect(self.paint_panel.reload_library)
        self.library_dialog.tabs.setCurrentIndex(1 if palettes else 0)
        self.library_dialog.show()
        self.library_dialog.raise_()
        self.library_dialog.activateWindow()

    def change_library_location(self) -> None:
        self.open_paint_library()
        self.library_dialog.change_location()

    def _on_app_state_changed(self, state) -> None:
        if state == Qt.ApplicationActive:
            self.reload_library_if_changed()

    def reload_library_if_changed(self) -> bool:
        """Pick up changes Dropbox synced in from another computer. Checked
        whenever the app comes to the front."""
        library = self.paint_library
        if not library.changed_on_disk():
            return False
        try:
            fresh = PaintLibrary.load(library.path)
        except (OSError, ValueError, TypeError, KeyError):
            return False  # mid-sync or damaged: try again next time
        library.replace_with(fresh)
        self.paint_panel.reload_library()
        if self.library_dialog is not None:
            self.library_dialog.refresh()
            self.library_dialog.refresh_palettes()
        self.statusBar().showMessage("Paint library reloaded: it was changed on another computer.")
        return True

    def _update_paint_target(self) -> None:
        swatch = self.doc.project.get_swatch(self._selected_swatch_id) if self.doc else None
        self.paint_panel.set_target(swatch.rgb if swatch else None)

    def _simplified(self, layer: Layer):
        """(Simplified, pixmap, lab) when Simplify is on and `layer` is the selected layer."""
        settings = self.doc.project.simplify
        if not settings.enabled or layer.id != self.doc.project.active_layer_id:
            return None
        return self.cache.simplified(self.doc, layer, self._canvas_size, settings.key())

    def _highlight_overlays(self) -> list:
        """Per layer, what is drawn over it: highlights (each swatch in its
        own color) or else the simplified image."""
        project = self.doc.project
        overlays = []
        for layer in project.layers:
            simplified = self._simplified(layer)
            colors = [(s.rgb, color_study.highlight_color(i)) for i, s in enumerate(project.swatches)
                      if s.highlight and s.layer_id == layer.id]
            pixmap = None
            if colors:
                pixmap = self.cache.highlight_pixmap(self.doc, layer, self._canvas_size, colors,
                                                     project.highlight_tolerance,
                                                     project.simplify.key() if simplified else None)
            elif simplified is not None:
                pixmap = simplified[1]
            if pixmap is not None:
                overlays.append((layer.id, pixmap))
        return overlays

    def _on_simplify_changed(self, settings) -> None:
        if self.doc is None:
            return
        self.doc.project.simplify = settings
        self._refresh_canvas()
        self._schedule_autosave()

    def _show_simplified_palette(self) -> None:
        layer = self._active_layer()
        simplified = self._simplified(layer) if layer is not None else None
        result = simplified[0] if simplified else None
        self.color_panel.show_simplified(result.colors if result else [], result.shares if result else [])

    def _add_simplified_swatches(self) -> None:
        layer = self._active_layer()
        simplified = self._simplified(layer) if layer is not None else None
        if simplified is None:
            return
        result = simplified[0]
        existing = {s.rgb for s in self.doc.project.swatches if s.layer_id == layer.id}
        points = color_study.region_points(result.labels, len(result.colors))
        new = [Swatch(new_id("swatch"), layer.id, uv[0], uv[1], rgb)
               for rgb, uv in zip(result.colors, points) if uv is not None and rgb not in existing]
        if not new:
            self.statusBar().showMessage("Those colors are already swatches.")
            return
        self._record()
        self.doc.project.swatches.extend(new)
        self._selected_swatch_id = new[0].id
        self._refresh_color_study()
        self.statusBar().showMessage(f"Added {len(new)} swatches from the simplified colors.")
        self._schedule_autosave()

    def _update_markers(self) -> None:
        project = self.doc.project
        self.canvas_view.set_markers([
            Marker(s.id, number, s.layer_id, s.u, s.v, s.rgb, s.id == self._selected_swatch_id,
                   color_study.highlight_color(number - 1) if s.highlight else None)
            for number, s in enumerate(project.swatches, start=1)
        ])
