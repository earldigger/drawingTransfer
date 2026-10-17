from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QVBoxLayout,
)

from ..models import GridSettings

PRESETS = {
    "3 x 3": (3, 3),
    "4 x 5": (4, 5),
    "8 x 10": (8, 10),
    "Custom": None,
}


class GridPanel(QWidget):
    gridChanged = Signal(object)  # GridSettings

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False

        layout = QVBoxLayout(self)
        box = QGroupBox("Grid Overlay")
        layout.addWidget(box)
        form = QFormLayout(box)

        self.enabled = QCheckBox("Show grid")
        form.addRow(self.enabled)

        self.preset = QComboBox()
        self.preset.addItems(PRESETS.keys())
        form.addRow("Preset", self.preset)

        self.rows = QSpinBox()
        self.rows.setRange(1, 50)
        self.rows.setValue(4)
        form.addRow("Horizontal divisions (rows)", self.rows)

        self.columns = QSpinBox()
        self.columns.setRange(1, 50)
        self.columns.setValue(4)
        form.addRow("Vertical divisions (columns)", self.columns)

        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setValue(60)
        self.opacity.setSuffix(" %")
        form.addRow("Opacity", self.opacity)

        self.thickness = QDoubleSpinBox()
        self.thickness.setRange(0.5, 20)
        self.thickness.setValue(2)
        self.thickness.setSingleStep(0.5)
        form.addRow("Line thickness (px)", self.thickness)

        self.enabled.toggled.connect(self._emit_change)
        self.rows.valueChanged.connect(self._on_manual_division_change)
        self.columns.valueChanged.connect(self._on_manual_division_change)
        self.opacity.valueChanged.connect(self._emit_change)
        self.thickness.valueChanged.connect(self._emit_change)
        self.preset.currentTextChanged.connect(self._on_preset_changed)

    def set_grid(self, grid: GridSettings) -> None:
        self._updating = True
        self.enabled.setChecked(grid.enabled)
        self.rows.setValue(grid.rows)
        self.columns.setValue(grid.columns)
        self.opacity.setValue(grid.opacity * 100)
        self.thickness.setValue(grid.thickness_px)
        self._sync_preset_label(grid.rows, grid.columns)
        self._updating = False

    def current_grid(self) -> GridSettings:
        return GridSettings(
            enabled=self.enabled.isChecked(),
            rows=self.rows.value(),
            columns=self.columns.value(),
            opacity=self.opacity.value() / 100.0,
            thickness_px=self.thickness.value(),
        )

    def _sync_preset_label(self, rows: int, columns: int) -> None:
        for label, dims in PRESETS.items():
            if dims == (rows, columns):
                self.preset.blockSignals(True)
                self.preset.setCurrentText(label)
                self.preset.blockSignals(False)
                return
        self.preset.blockSignals(True)
        self.preset.setCurrentText("Custom")
        self.preset.blockSignals(False)

    def _on_preset_changed(self, label: str):
        dims = PRESETS.get(label)
        if dims is None or self._updating:
            return
        rows, columns = dims
        self._updating = True
        self.rows.setValue(rows)
        self.columns.setValue(columns)
        self._updating = False
        self._emit_change()

    def _on_manual_division_change(self, *_args):
        if not self._updating:
            self._sync_preset_label(self.rows.value(), self.columns.value())
        self._emit_change()

    def _emit_change(self, *_args):
        if self._updating:
            return
        self.gridChanged.emit(self.current_grid())
