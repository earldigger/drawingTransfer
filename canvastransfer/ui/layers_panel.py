from __future__ import annotations

import math
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..models import Adjustments, BlendMode, Layer, Project

LAYER_ID_ROLE = Qt.UserRole + 1
MIN_LEVELS_GAP = 2

BLEND_LABELS = [
    (BlendMode.NORMAL, "Normal"),
    (BlendMode.MULTIPLY, "Multiply"),
    (BlendMode.SCREEN, "Screen"),
    (BlendMode.LINEAR_LIGHT, "Linear Light"),
]


def gamma_to_slider(gamma: float) -> int:
    return round(100 * math.log10(max(gamma, 1e-3)))


def slider_to_gamma(value: int) -> float:
    return round(10 ** (value / 100), 3)


class _SliderRow:
    """Label | slider | value readout, laid into a grid row."""

    def __init__(self, grid: QGridLayout, row: int, label: str, lo: int, hi: int, value: int, fmt, tooltip: str = ""):
        self.label = QLabel(label)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(value)
        self.readout = QLabel()
        self.readout.setMinimumWidth(40)
        self.readout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._fmt = fmt
        if tooltip:
            for w in (self.label, self.slider):
                w.setToolTip(tooltip)
        self.slider.valueChanged.connect(self._show)
        self._show(value)
        grid.addWidget(self.label, row, 0)
        grid.addWidget(self.slider, row, 1)
        grid.addWidget(self.readout, row, 2)

    def _show(self, value: int) -> None:
        self.readout.setText(self._fmt(value))

    def set(self, value: int) -> None:
        self.slider.setValue(value)
        self._show(value)


# Track colors like Photoshop's Camera Raw sliders: each shows which way it shifts.
TEMPERATURE_TRACK = ["#2a3cff", "#8a8a8a", "#f4ef1c"]
TINT_TRACK = ["#22e022", "#8a8a8a", "#f020f0"]
SATURATION_TRACK = ["#7c7c7c", "#7f9a72", "#d8c870", "#c8503c"]


def _track_style(colors: list[str]) -> str:
    stops = ", ".join(f"stop:{i / (len(colors) - 1):.2f} {c}" for i, c in enumerate(colors))
    return (
        "QSlider::groove:horizontal { height: 4px; border-radius: 2px;"
        f" background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {stops}); }}"
        "QSlider::handle:horizontal { background: #f2f2f2; border: 1px solid #5a5a5a;"
        " width: 12px; margin: -6px 0; border-radius: 3px; }"
        "QSlider::handle:horizontal:disabled { background: #b0b0b0; }"
    )


class _GradientSliderRow:
    """Photoshop-style control: label with an editable number box on top,
    colored track below. Slider and box stay in sync."""

    def __init__(self, layout: QVBoxLayout, label: str, colors: list[str], tooltip: str = ""):
        top = QHBoxLayout()
        self.label = QLabel(f"{label}:")
        self.spin = QSpinBox()
        self.spin.setRange(-100, 100)
        self.spin.setButtonSymbols(QSpinBox.NoButtons)
        self.spin.setAlignment(Qt.AlignRight)
        self.spin.setFixedWidth(64)
        self.spin.setKeyboardTracking(False)  # apply on Return / focus-out, not each keystroke
        top.addWidget(self.label)
        top.addStretch(1)
        top.addWidget(self.spin)
        layout.addLayout(top)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(-100, 100)
        self.slider.setStyleSheet(_track_style(colors))
        layout.addWidget(self.slider)
        if tooltip:
            for w in (self.label, self.slider, self.spin):
                w.setToolTip(tooltip)

        self.slider.valueChanged.connect(self._slider_moved)
        self.spin.valueChanged.connect(self.slider.setValue)

    def _slider_moved(self, value: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        self.spin.blockSignals(False)

    def set(self, value: int) -> None:
        self.slider.setValue(value)
        self._slider_moved(value)


class LayersPanel(QWidget):
    layerSelected = Signal(str)
    layerVisibilityToggled = Signal(str, bool)
    layerOpacityChanged = Signal(str, float)
    layerBlendModeChanged = Signal(str, str)
    # layer id, new Adjustments, slider name ("" = discrete change; same
    # name in quick succession is merged into one undo step)
    layerAdjustmentsChanged = Signal(str, object, str)
    addLayerRequested = Signal()
    deleteLayerRequested = Signal(str)
    moveLayerUpRequested = Signal(str)
    moveLayerDownRequested = Signal(str)
    renameLayerRequested = Signal(str, str)
    perspectiveCorrectRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._adjust = Adjustments()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_layers_box())
        layout.addWidget(self._build_appearance_box())
        layout.addWidget(self._build_levels_box())
        layout.addWidget(self._build_color_box())
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

        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add Image…")
        self.delete_button = QPushButton("Delete")
        self.up_button = QPushButton("↑")
        self.down_button = QPushButton("↓")
        for b in (self.add_button, self.delete_button, self.up_button, self.down_button):
            buttons.addWidget(b)
        v.addLayout(buttons)
        self.add_button.clicked.connect(self.addLayerRequested)
        self.delete_button.clicked.connect(lambda: self._emit_for_current(self.deleteLayerRequested))
        self.up_button.clicked.connect(lambda: self._emit_for_current(self.moveLayerUpRequested))
        self.down_button.clicked.connect(lambda: self._emit_for_current(self.moveLayerDownRequested))

        self.perspective_button = QPushButton("Perspective Correct…")
        self.perspective_button.clicked.connect(lambda: self._emit_for_current(self.perspectiveCorrectRequested))
        v.addWidget(self.perspective_button)
        return box

    def _build_appearance_box(self) -> QGroupBox:
        box = QGroupBox("Layer Appearance")
        grid = QGridLayout(box)
        self.opacity = _SliderRow(grid, 0, "Opacity", 0, 100, 100, lambda v: f"{v}%")
        self.opacity_slider = self.opacity.slider
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)

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
        self.invert_check.toggled.connect(self._on_invert_toggled)
        v.addWidget(self.invert_check)

        grid = QGridLayout()
        v.addLayout(grid)
        self.black = _SliderRow(grid, 0, "Dark point", 0, 255 - MIN_LEVELS_GAP, 0, str,
                                "Values at or below this become black")
        self.gamma = _SliderRow(grid, 1, "Midtones", -100, 100, 0, lambda s: f"{slider_to_gamma(s):.2f}",
                                "Right lightens the middle values, left darkens them")
        self.white = _SliderRow(grid, 2, "Light point", MIN_LEVELS_GAP, 255, 255, str,
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

    def _build_color_box(self) -> QGroupBox:
        box = QGroupBox("Color && Vibrance")
        v = QVBoxLayout(box)
        self.temperature = _GradientSliderRow(v, "Temperature", TEMPERATURE_TRACK, "Left bluer, right yellower")
        self.tint = _GradientSliderRow(v, "Tint", TINT_TRACK, "Left greener, right more magenta")
        v.addSpacing(6)
        self.vibrance = _GradientSliderRow(v, "Vibrance", SATURATION_TRACK,
                                           "Changes muted colors most and leaves strong colors mostly alone")
        self.saturation = _GradientSliderRow(v, "Saturation", SATURATION_TRACK, "-100 is fully gray")
        self._color_rows = {
            "temperature": self.temperature, "tint": self.tint,
            "vibrance": self.vibrance, "saturation": self.saturation,
        }
        for name, row in self._color_rows.items():
            row.slider.valueChanged.connect(
                lambda s, n=name: self._emit_adjust(n, replace(self._adjust, **{n: s / 100.0}))
            )
        self.color_reset = QPushButton("Reset Color")
        self.color_reset.clicked.connect(
            lambda: self._emit_adjust("", replace(self._adjust, **{n: 0.0 for n in self._color_rows}), sync=True)
        )
        v.addWidget(self.color_reset, alignment=Qt.AlignRight)
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
        if layer is not None:
            self.opacity.set(round(layer.opacity * 100))
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
        for name, row in self._color_rows.items():
            row.set(round(getattr(adj, name) * 100))
        self._updating = was_updating

    def _set_layer_controls_enabled(self, enabled: bool) -> None:
        widgets = [
            self.opacity_slider, self.blend_combo, self.delete_button, self.up_button, self.down_button,
            self.perspective_button, self.invert_check, self.black.slider, self.gamma.slider, self.white.slider,
            self.levels_reset, self.color_reset,
        ]
        for row in self._color_rows.values():
            widgets += [row.slider, row.spin]
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

    def _emit_adjust(self, slider_name: str, adj: Adjustments, sync: bool = False) -> None:
        if self._updating:
            return
        layer_id = self._current_layer_id()
        if not layer_id or adj == self._adjust:
            return
        self._adjust = adj
        if sync:
            self._show_adjustments(adj)
        self.layerAdjustmentsChanged.emit(layer_id, adj, slider_name)

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

    def _on_invert_toggled(self, checked: bool) -> None:
        self._emit_adjust("", replace(self._adjust, invert=checked))

    def _on_current_changed(self, current, _previous):
        if self._updating or current is None:
            return
        self.layerSelected.emit(current.data(LAYER_ID_ROLE))

    def _on_item_changed(self, item: QListWidgetItem):
        if self._updating:
            return
        self.layerVisibilityToggled.emit(item.data(LAYER_ID_ROLE), item.checkState() == Qt.Checked)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        new_name, ok = QInputDialog.getText(self, "Rename Layer", "Name:", text=item.text())
        if ok and new_name.strip():
            self.renameLayerRequested.emit(item.data(LAYER_ID_ROLE), new_name.strip())

    def _on_opacity_changed(self, value: int):
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
