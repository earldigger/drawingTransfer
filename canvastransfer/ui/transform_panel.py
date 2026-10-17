from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QDoubleSpinBox,
    QCheckBox,
    QGroupBox,
    QVBoxLayout,
)

from ..models import Transform


class TransformPanel(QWidget):
    """Move / proportional or independent scale / rotate / skew controls
    for the active layer. Dragging on the canvas also edits offset_x/y;
    `set_transform` updates these fields without re-emitting a change.
    """

    transformChanged = Signal(object)  # Transform

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False

        layout = QVBoxLayout(self)
        box = QGroupBox("Transform")
        layout.addWidget(box)
        form = QFormLayout(box)

        self.offset_x = self._spin(-5000, 5000)
        self.offset_y = self._spin(-5000, 5000)
        form.addRow("Position X", self.offset_x)
        form.addRow("Position Y", self.offset_y)

        self.lock_scale = QCheckBox("Proportional scale")
        self.lock_scale.setChecked(True)
        form.addRow(self.lock_scale)

        self.scale_x = self._spin(0.01, 20, value=1.0, step=0.05)
        self.scale_y = self._spin(0.01, 20, value=1.0, step=0.05)
        form.addRow("Scale X", self.scale_x)
        form.addRow("Scale Y", self.scale_y)

        self.rotation = self._spin(-360, 360, value=0.0, step=1.0)
        form.addRow("Rotation (°)", self.rotation)

        self.skew_x = self._spin(-85, 85, value=0.0, step=1.0)
        self.skew_y = self._spin(-85, 85, value=0.0, step=1.0)
        form.addRow("Skew X (°)", self.skew_x)
        form.addRow("Skew Y (°)", self.skew_y)

        self.setEnabled(False)

        for spin in (self.offset_x, self.offset_y, self.rotation, self.skew_x, self.skew_y):
            spin.valueChanged.connect(self._emit_change)
        self.scale_x.valueChanged.connect(self._on_scale_x_changed)
        self.scale_y.valueChanged.connect(self._emit_change)
        self.lock_scale.toggled.connect(self._on_lock_toggled)

    @staticmethod
    def _spin(lo, hi, value=0.0, step=1.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(value)
        spin.setSingleStep(step)
        spin.setDecimals(2)
        return spin

    def set_transform(self, transform: Transform) -> None:
        self._updating = True
        self.offset_x.setValue(transform.offset_x)
        self.offset_y.setValue(transform.offset_y)
        self.scale_x.setValue(transform.scale_x)
        self.scale_y.setValue(transform.scale_y)
        self.rotation.setValue(transform.rotation_deg)
        self.skew_x.setValue(transform.skew_x_deg)
        self.skew_y.setValue(transform.skew_y_deg)
        self._updating = False

    def current_transform(self) -> Transform:
        return Transform(
            offset_x=self.offset_x.value(),
            offset_y=self.offset_y.value(),
            scale_x=self.scale_x.value(),
            scale_y=self.scale_y.value(),
            rotation_deg=self.rotation.value(),
            skew_x_deg=self.skew_x.value(),
            skew_y_deg=self.skew_y.value(),
        )

    def nudge_offset(self, dx: float, dy: float) -> None:
        self._updating = True
        self.offset_x.setValue(self.offset_x.value() + dx)
        self.offset_y.setValue(self.offset_y.value() + dy)
        self._updating = False
        self._emit_change()

    def _on_lock_toggled(self, locked: bool):
        if locked:
            self._updating = True
            self.scale_y.setValue(self.scale_x.value())
            self._updating = False
        self.scale_y.setEnabled(not locked)
        self._emit_change()

    def _on_scale_x_changed(self, value: float):
        if self.lock_scale.isChecked() and not self._updating:
            self._updating = True
            self.scale_y.setValue(value)
            self._updating = False
        self._emit_change()

    def _emit_change(self, *_args):
        if self._updating:
            return
        self.transformChanged.emit(self.current_transform())
