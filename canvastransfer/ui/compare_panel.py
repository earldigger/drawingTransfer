from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QSlider,
    QGroupBox,
    QVBoxLayout,
    QLabel,
)
from PySide6.QtCore import Qt

from ..models import CompareMode, Project


class ComparePanel(QWidget):
    """Overlay / Blink / Split comparison between two chosen layers --
    typically the source drawing and the latest canvas photo.
    """

    settingsChanged = Signal()  # re-read via current_* methods

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False

        layout = QVBoxLayout(self)
        box = QGroupBox("Compare")
        layout.addWidget(box)
        form = QFormLayout(box)

        self.mode = QComboBox()
        self.mode.addItem("Overlay (normal stack)", CompareMode.OVERLAY.value)
        self.mode.addItem("Blink", CompareMode.BLINK.value)
        self.mode.addItem("Split View", CompareMode.SPLIT.value)
        form.addRow("Mode", self.mode)

        self.layer_a = QComboBox()
        self.layer_b = QComboBox()
        form.addRow("Layer A", self.layer_a)
        form.addRow("Layer B", self.layer_b)

        self.blink_interval = QSpinBox()
        self.blink_interval.setRange(100, 5000)
        self.blink_interval.setValue(600)
        self.blink_interval.setSuffix(" ms")
        form.addRow("Blink interval", self.blink_interval)

        self.split_position = QSlider(Qt.Horizontal)
        self.split_position.setRange(0, 100)
        self.split_position.setValue(50)
        self.split_label = QLabel("50%")
        self.split_position.valueChanged.connect(
            lambda v: self.split_label.setText(f"{v}%")
        )
        form.addRow("Split position", self.split_position)
        form.addRow("", self.split_label)

        for widget in (self.mode, self.layer_a, self.layer_b, self.blink_interval, self.split_position):
            if hasattr(widget, "currentIndexChanged"):
                widget.currentIndexChanged.connect(self._emit_change)
            elif hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._emit_change)

    def refresh_layers(self, project: Project) -> None:
        self._updating = True
        for combo, selected in ((self.layer_a, project.compare_layer_a), (self.layer_b, project.compare_layer_b)):
            combo.clear()
            for layer in project.layers:
                combo.addItem(layer.name, layer.id)
            if selected and combo.findData(selected) >= 0:
                combo.setCurrentIndex(combo.findData(selected))
        idx = self.mode.findData(project.compare_mode.value)
        if idx >= 0:
            self.mode.setCurrentIndex(idx)
        self.split_position.setValue(round(project.split_position * 100))
        self._updating = False

    def current_mode(self) -> CompareMode:
        return CompareMode(self.mode.currentData())

    def current_layer_a_id(self) -> str | None:
        return self.layer_a.currentData()

    def current_layer_b_id(self) -> str | None:
        return self.layer_b.currentData()

    def current_split_position(self) -> float:
        return self.split_position.value() / 100.0

    def current_blink_interval_ms(self) -> int:
        return self.blink_interval.value()

    def _emit_change(self, *_args):
        if not self._updating:
            self.settingsChanged.emit()
