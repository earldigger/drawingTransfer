from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QComboBox,
    QLabel,
    QGroupBox,
    QInputDialog,
)

from ..models import Project, BlendMode

LAYER_ID_ROLE = Qt.UserRole + 1


class LayersPanel(QWidget):
    layerSelected = Signal(str)
    layerVisibilityToggled = Signal(str, bool)
    layerOpacityChanged = Signal(str, float)
    layerBlendModeChanged = Signal(str, str)
    addLayerRequested = Signal()
    deleteLayerRequested = Signal(str)
    moveLayerUpRequested = Signal(str)
    moveLayerDownRequested = Signal(str)
    renameLayerRequested = Signal(str, str)
    perspectiveCorrectRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False

        layout = QVBoxLayout(self)
        box = QGroupBox("Layers")
        layout.addWidget(box)
        box_layout = QVBoxLayout(box)

        self.list_widget = QListWidget()
        self.list_widget.itemChanged.connect(self._on_item_changed)
        self.list_widget.currentItemChanged.connect(self._on_current_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        box_layout.addWidget(self.list_widget)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add Image…")
        self.delete_button = QPushButton("Delete")
        self.up_button = QPushButton("↑")
        self.down_button = QPushButton("↓")
        for b in (self.add_button, self.delete_button, self.up_button, self.down_button):
            buttons.addWidget(b)
        box_layout.addLayout(buttons)

        self.add_button.clicked.connect(self.addLayerRequested)
        self.delete_button.clicked.connect(self._emit_delete)
        self.up_button.clicked.connect(self._emit_move_up)
        self.down_button.clicked.connect(self._emit_move_down)

        self.perspective_button = QPushButton("Perspective Correct…")
        self.perspective_button.clicked.connect(self._emit_perspective)
        box_layout.addWidget(self.perspective_button)

        appearance = QGroupBox("Layer Appearance")
        layout.addWidget(appearance)
        appearance_layout = QVBoxLayout(appearance)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_value_label = QLabel("100%")
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_value_label)
        appearance_layout.addLayout(opacity_row)

        blend_row = QHBoxLayout()
        blend_row.addWidget(QLabel("Blend Mode"))
        self.blend_combo = QComboBox()
        self.blend_combo.addItem("Normal", BlendMode.NORMAL.value)
        self.blend_combo.addItem("Multiply", BlendMode.MULTIPLY.value)
        self.blend_combo.currentIndexChanged.connect(self._on_blend_changed)
        blend_row.addWidget(self.blend_combo)
        appearance_layout.addLayout(blend_row)

        self._set_appearance_enabled(False)

    # -- outward-facing API ------------------------------------------------

    def refresh(self, project: Project) -> None:
        self._updating = True
        self.list_widget.clear()
        for layer in reversed(project.layers):  # top of stack shown first
            item = QListWidgetItem(layer.name)
            item.setData(LAYER_ID_ROLE, layer.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked)
            self.list_widget.addItem(item)
            if layer.id == project.active_layer_id:
                self.list_widget.setCurrentItem(item)

        active = project.get_layer(project.active_layer_id) if project.active_layer_id else None
        self._updating = False
        self.sync_appearance(active)

    def sync_appearance(self, layer) -> None:
        self._updating = True
        if layer is not None:
            self._set_appearance_enabled(True)
            self.opacity_slider.setValue(round(layer.opacity * 100))
            self.blend_combo.setCurrentIndex(self.blend_combo.findData(layer.blend_mode.value))
        else:
            self._set_appearance_enabled(False)
        self._updating = False

    def _set_appearance_enabled(self, enabled: bool) -> None:
        self.opacity_slider.setEnabled(enabled)
        self.blend_combo.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        self.up_button.setEnabled(enabled)
        self.down_button.setEnabled(enabled)
        self.perspective_button.setEnabled(enabled)

    # -- internal handlers ---------------------------------------------

    def _current_layer_id(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.data(LAYER_ID_ROLE) if item else None

    def _on_current_changed(self, current, _previous):
        if self._updating or current is None:
            return
        self.layerSelected.emit(current.data(LAYER_ID_ROLE))

    def _on_item_changed(self, item: QListWidgetItem):
        if self._updating:
            return
        layer_id = item.data(LAYER_ID_ROLE)
        self.layerVisibilityToggled.emit(layer_id, item.checkState() == Qt.Checked)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        layer_id = item.data(LAYER_ID_ROLE)
        new_name, ok = QInputDialog.getText(self, "Rename Layer", "Name:", text=item.text())
        if ok and new_name.strip():
            self.renameLayerRequested.emit(layer_id, new_name.strip())

    def _on_opacity_changed(self, value: int):
        self.opacity_value_label.setText(f"{value}%")
        if self._updating:
            return
        layer_id = self._current_layer_id()
        if layer_id:
            self.layerOpacityChanged.emit(layer_id, value / 100.0)

    def _on_blend_changed(self, _index: int):
        if self._updating:
            return
        layer_id = self._current_layer_id()
        if layer_id:
            self.layerBlendModeChanged.emit(layer_id, self.blend_combo.currentData())

    def _emit_delete(self):
        layer_id = self._current_layer_id()
        if layer_id:
            self.deleteLayerRequested.emit(layer_id)

    def _emit_move_up(self):
        layer_id = self._current_layer_id()
        if layer_id:
            self.moveLayerUpRequested.emit(layer_id)

    def _emit_move_down(self):
        layer_id = self._current_layer_id()
        if layer_id:
            self.moveLayerDownRequested.emit(layer_id)

    def _emit_perspective(self):
        layer_id = self._current_layer_id()
        if layer_id:
            self.perspectiveCorrectRequested.emit(layer_id)
