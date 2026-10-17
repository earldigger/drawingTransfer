from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QDoubleSpinBox,
    QComboBox,
    QDialogButtonBox,
    QVBoxLayout,
)

from ..models import Units


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.name_edit = QLineEdit("Untitled Project")
        form.addRow("Project name", self.name_edit)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.1, 10000)
        self.width_spin.setValue(16)
        form.addRow("Canvas width", self.width_spin)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.1, 10000)
        self.height_spin.setValue(20)
        form.addRow("Canvas height", self.height_spin)

        self.units_combo = QComboBox()
        self.units_combo.addItem("Inches", Units.INCHES.value)
        self.units_combo.addItem("Centimeters", Units.CENTIMETERS.value)
        form.addRow("Units", self.units_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, float, float, Units]:
        return (
            self.name_edit.text().strip() or "Untitled Project",
            self.width_spin.value(),
            self.height_spin.value(),
            Units(self.units_combo.currentData()),
        )
