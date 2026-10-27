from __future__ import annotations

import math
from dataclasses import replace

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..models import Adjustments, BlendMode, Layer, LayerKind, Project
from .slider_row import ValueSliderRow

LAYER_ID_ROLE = Qt.UserRole + 1
MIN_LEVELS_GAP = 2

BLEND_LABELS = [
    (BlendMode.NORMAL, "Normal"),
    (BlendMode.MULTIPLY, "Multiply"),
    (BlendMode.SCREEN, "Screen"),
    (BlendMode.LINEAR_LIGHT, "Linear Light"),
]

# Track colors like Photoshop's sliders: each shows what moving that way does.
HUE_TRACK = ["#ff0000", "#ffff00", "#00ff00", "#00ffff", "#0000ff", "#ff00ff", "#ff0000"]
SATURATION_TRACK = ["#7c7c7c", "#6aa7a0", "#3048ff", "#c020d8", "#ff2020"]
LIGHTNESS_TRACK = ["#000000", "#808080", "#ffffff"]
VALUE_TRACK = ["#000000", "#ffffff"]
MIDTONE_TRACK = ["#303030", "#d0d0d0"]


def gamma_to_slider(gamma: float) -> int:
    return round(100 * math.log10(max(gamma, 1e-3)))


def slider_to_gamma(value: int) -> float:
    return round(10 ** (value / 100), 2)


class LayersPanel(QWidget):
    layerSelected = Signal(str)
    layerVisibilityToggled = Signal(str, bool)
    layerOpacityChanged = Signal(str, float)
    layerBlendModeChanged = Signal(str, str)
    # layer id, new Adjustments, control name ("" = discrete change; the same
    # name in quick succession is merged into one undo step)
    layerAdjustmentsChanged = Signal(str, object, str)
    addLayerRequested = Signal(str)  # a LayerKind value
    deleteLayerRequested = Signal(str)
    moveLayerUpRequested = Signal(str)
    moveLayerDownRequested = Signal(str)
    renameLayerRequested = Signal(str, str)
    perspectiveCorrectRequested = Signal(str)
    cropRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._adjust = Adjustments()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_layers_box())
        layout.addWidget(self._build_appearance_box())
        layout.addWidget(self._build_levels_box())
        layout.addWidget(self._build_hue_box())
        self._set_layer_controls_enabled(False)

    # -- construction -----------------------------------------------------

    def _build_layers_box(self) -> QGroupBox:
        box = QGroupBox("Layers")
        v = QVBoxLayout(box)
        self.list_widget = QListWidget()
        self.list_widget.itemChanged.connect(self._on_item_changed)
        self.list_widget.currentItemChanged.connect(self._on_current_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        v.addWidget(self.list_widget)

        adds = QHBoxLayout()
        self.add_canvas_button = QPushButton("Add Canvas Photo…")
        self.add_canvas_button.setToolTip("A photo of your canvas: you set its corners and it fills the canvas")
        self.add_button = QPushButton("Add Reference…")
        self.add_button.setToolTip("The photo or drawing to transfer: added on top at Multiply 60 %")
        adds.addWidget(self.add_canvas_button)
        adds.addWidget(self.add_button)
        v.addLayout(adds)
        buttons = QHBoxLayout()
        self.delete_button = QPushButton("Delete")
        self.up_button = QPushButton("↑")
        self.down_button = QPushButton("↓")
        for b in (self.delete_button, self.up_button, self.down_button):
            buttons.addWidget(b)
        v.addLayout(buttons)
        self.add_canvas_button.clicked.connect(lambda: self.addLayerRequested.emit(LayerKind.CANVAS.value))
        self.add_button.clicked.connect(lambda: self.addLayerRequested.emit(LayerKind.REFERENCE.value))
        self.delete_button.clicked.connect(lambda: self._emit_for_current(self.deleteLayerRequested))
        self.up_button.clicked.connect(lambda: self._emit_for_current(self.moveLayerUpRequested))
        self.down_button.clicked.connect(lambda: self._emit_for_current(self.moveLayerDownRequested))

        corners_row = QHBoxLayout()
        self.perspective_button = QPushButton("Edit Corners…")
        self.perspective_button.clicked.connect(lambda: self._emit_for_current(self.perspectiveCorrectRequested))
        self.crop_button = QPushButton("Crop…")
        self.crop_button.setToolTip("Trim the selected reference (⌥⌘K). Canvas photos are cropped by their corners")
        self.crop_button.clicked.connect(lambda: self._emit_for_current(self.cropRequested))
        corners_row.addWidget(self.perspective_button)
        corners_row.addWidget(self.crop_button)
        v.addLayout(corners_row)
        return box

    def _build_appearance_box(self) -> QGroupBox:
        box = QGroupBox("Look")
        grid = QGridLayout(box)
        grid.addWidget(QLabel("Opacity"), 0, 0)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_label = QLabel("100%")
        self.opacity_label.setMinimumWidth(40)
        self.opacity_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        grid.addWidget(self.opacity_slider, 0, 1)
        grid.addWidget(self.opacity_label, 0, 2)

        grid.addWidget(QLabel("Blend Mode"), 1, 0)
        self.blend_combo = QComboBox()
        for mode, label in BLEND_LABELS:
            self.blend_combo.addItem(label, mode.value)
        self.blend_combo.currentIndexChanged.connect(self._on_blend_changed)
        grid.addWidget(self.blend_combo, 1, 1, 1, 2)
        return box

    def _build_levels_box(self) -> QGroupBox:
        box = QGroupBox("Levels")
        v = QVBoxLayout(box)
        self.invert_check = QCheckBox("Invert values")
        self.invert_check.toggled.connect(lambda c: self._emit_adjust("", replace(self._adjust, invert=c)))
        v.addWidget(self.invert_check)

        self.black = ValueSliderRow(v, "Dark point", 0, 255 - MIN_LEVELS_GAP, 0, VALUE_TRACK,
                                     "Values at or below this become black")
        self.gamma = ValueSliderRow(v, "Midtones", -100, 100, 0, MIDTONE_TRACK,
                                     "Right lightens the middle values, left darkens them (1.00 = unchanged)",
                                     decimals=2, to_display=slider_to_gamma, from_display=lambda g: gamma_to_slider(g))
        self.white = ValueSliderRow(v, "Light point", MIN_LEVELS_GAP, 255, 255, VALUE_TRACK,
                                     "Values at or above this become white")
        self.black.slider.valueChanged.connect(self._on_black_changed)
        self.gamma.slider.valueChanged.connect(
            lambda s: self._emit_adjust("gamma", replace(self._adjust, gamma=slider_to_gamma(s)))
        )
        self.white.slider.valueChanged.connect(self._on_white_changed)

        self.levels_reset = QPushButton("Reset Levels")
        self.levels_reset.clicked.connect(
            lambda: self._emit_adjust("", replace(self._adjust, black=0, gamma=1.0, white=255), sync=True)
        )
        v.addWidget(self.levels_reset, alignment=Qt.AlignRight)
        return box

    def _build_hue_box(self) -> QGroupBox:
        box = QGroupBox("Hue / Saturation")
        v = QVBoxLayout(box)
        self.hue = ValueSliderRow(v, "Hue", -180, 180, 0, HUE_TRACK, "Shifts every color around the color wheel")
        self.saturation = ValueSliderRow(v, "Saturation", -100, 100, 0, SATURATION_TRACK, "-100 is fully gray")
        self.lightness = ValueSliderRow(v, "Lightness", -100, 100, 0, LIGHTNESS_TRACK,
                                         "+100 is white, -100 is black")
        self.colorize_check = QCheckBox("Colorize")
        self.colorize_check.setToolTip("Tint the whole layer one color, keeping only its light and dark")
        v.addWidget(self.colorize_check)

        self.hue.slider.valueChanged.connect(lambda s: self._emit_adjust(
            "colorize_hue" if self._adjust.colorize else "hue",
            replace(self._adjust, **{"colorize_hue" if self._adjust.colorize else "hue": s})))
        self.saturation.slider.valueChanged.connect(lambda s: self._emit_adjust(
            "colorize_saturation" if self._adjust.colorize else "saturation",
            replace(self._adjust, **{"colorize_saturation" if self._adjust.colorize else "saturation": s})))
        self.lightness.slider.valueChanged.connect(
            lambda s: self._emit_adjust("lightness", replace(self._adjust, lightness=s)))
        self.colorize_check.toggled.connect(
            lambda c: self._emit_adjust("", replace(self._adjust, colorize=c), sync=True))

        self.hue_sat_reset = QPushButton("Reset Hue / Saturation")
        defaults = Adjustments()
        self.hue_sat_reset.clicked.connect(lambda: self._emit_adjust("", replace(
            self._adjust, hue=0, saturation=0, lightness=0, colorize=False,
            colorize_hue=defaults.colorize_hue, colorize_saturation=defaults.colorize_saturation), sync=True))
        v.addWidget(self.hue_sat_reset, alignment=Qt.AlignRight)
        return box

    # -- outward-facing API ------------------------------------------------

    def refresh(self, project: Project) -> None:
        self._updating = True
        self.list_widget.clear()
        for layer in reversed(project.layers):  # top of stack shown first
            item = QListWidgetItem(layer.name)
            item.setData(LAYER_ID_ROLE, layer.id)
            item.setFlags((item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            item.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked)
            self.list_widget.addItem(item)
            if layer.id == project.active_layer_id:
                self.list_widget.setCurrentItem(item)
        self._updating = False
        self.sync_appearance(project.get_layer(project.active_layer_id))

    def sync_appearance(self, layer: Layer | None) -> None:
        self._updating = True
        self._set_layer_controls_enabled(layer is not None)
        self.crop_button.setEnabled(layer is not None and layer.kind == LayerKind.REFERENCE)
        if layer is not None:
            self.opacity_slider.setValue(round(layer.opacity * 100))
            self.blend_combo.setCurrentIndex(self.blend_combo.findData(layer.blend_mode.value))
            self._show_adjustments(layer.adjustments)
        self._updating = False

    def _show_adjustments(self, adj: Adjustments) -> None:
        was_updating, self._updating = self._updating, True
        self._adjust = adj
        self.invert_check.setChecked(adj.invert)
        self.black.set(adj.black)
        self.gamma.set(gamma_to_slider(adj.gamma))
        self.white.set(adj.white)
        # Colorize reuses the Hue and Saturation sliders with Photoshop's colorize ranges.
        self.colorize_check.setChecked(adj.colorize)
        if adj.colorize:
            self.hue.set_range(0, 360)
            self.saturation.set_range(0, 100)
            self.hue.set(adj.colorize_hue)
            self.saturation.set(adj.colorize_saturation)
        else:
            self.hue.set_range(-180, 180)
            self.saturation.set_range(-100, 100)
            self.hue.set(adj.hue)
            self.saturation.set(adj.saturation)
        self.lightness.set(adj.lightness)
        self._updating = was_updating

    def _set_layer_controls_enabled(self, enabled: bool) -> None:
        widgets = [
            self.opacity_slider, self.blend_combo, self.delete_button, self.up_button, self.down_button,
            self.perspective_button, self.invert_check, self.levels_reset, self.colorize_check, self.hue_sat_reset,
        ]
        for row in (self.black, self.gamma, self.white, self.hue, self.saturation, self.lightness):
            widgets += row.widgets()
        for w in widgets:
            w.setEnabled(enabled)

    # -- internal handlers ---------------------------------------------

    def _current_layer_id(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.data(LAYER_ID_ROLE) if item else None

    def _emit_for_current(self, signal) -> None:
        layer_id = self._current_layer_id()
        if layer_id:
            signal.emit(layer_id)

    def _emit_adjust(self, control: str, adj: Adjustments, sync: bool = False) -> None:
        if self._updating:
            return
        layer_id = self._current_layer_id()
        if not layer_id or adj == self._adjust:
            return
        self._adjust = adj
        if sync:
            self._show_adjustments(adj)
        self.layerAdjustmentsChanged.emit(layer_id, adj, control)

    def _on_black_changed(self, value: int) -> None:
        if self._updating:
            return
        limit = self._adjust.white - MIN_LEVELS_GAP
        if value > limit:  # dark point can't pass the light point
            self._updating = True
            self.black.set(limit)
            self._updating = False
            value = limit
        self._emit_adjust("black", replace(self._adjust, black=value))

    def _on_white_changed(self, value: int) -> None:
        if self._updating:
            return
        limit = self._adjust.black + MIN_LEVELS_GAP
        if value < limit:
            self._updating = True
            self.white.set(limit)
            self._updating = False
            value = limit
        self._emit_adjust("white", replace(self._adjust, white=value))

    def _on_current_changed(self, current, _previous):
        if self._updating or current is None:
            return
        self.layerSelected.emit(current.data(LAYER_ID_ROLE))

    def _on_item_changed(self, item: QListWidgetItem):
        if self._updating:
            return
        # emitted after Qt has finished with this click: the handler rebuilds the
        # list, which would otherwise delete the item while its signal is running
        item_id, on = item.data(LAYER_ID_ROLE), item.checkState() == Qt.Checked
        QTimer.singleShot(0, lambda: self.layerVisibilityToggled.emit(item_id, on))

    def _on_item_double_clicked(self, item: QListWidgetItem):
        new_name, ok = QInputDialog.getText(self, "Rename Layer", "Name:", text=item.text())
        if ok and new_name.strip():
            self.renameLayerRequested.emit(item.data(LAYER_ID_ROLE), new_name.strip())

    def _on_opacity_changed(self, value: int):
        self.opacity_label.setText(f"{value}%")
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
