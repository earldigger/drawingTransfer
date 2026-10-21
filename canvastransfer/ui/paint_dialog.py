"""Add or edit one paint: names, pigments, opacity, and its masstone color
(pasted from artistpigments.org) or a stand-in paint to borrow color from."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from .. import color_study as cs
from ..paints import MEDIUM_LABELS, OPACITY_LABELS, Paint, PaintLibrary, medium_label, new_manual_id, parse_lab_text

OFF_SCREEN_NOTE = "⚠ Brighter or more saturated than a screen can show; shown and mixed as the nearest screen color."


def paint_chip(rgb, size: int = 18, dashed: bool = False) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if rgb is None:
        p.setPen(QPen(QColor(140, 140, 140), 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
    else:
        p.setPen(QPen(QColor(90, 90, 90), 1, Qt.DashLine if dashed else Qt.SolidLine))
        p.setBrush(QColor(*rgb))
    p.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    p.end()
    return QIcon(pm)


def chip_style(rgb) -> str:
    return f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]}); border: 1px solid #666; border-radius: 4px;"


class PaintDialog(QDialog):
    def __init__(self, library: PaintLibrary, paint: Paint | None = None, medium: str = "oil", parent=None):
        super().__init__(parent)
        self.library = library
        self.paint = paint
        self.setWindowTitle("Edit Paint" if paint else "Add Paint")
        self.setMinimumWidth(520)

        form = QFormLayout()
        self.medium = QComboBox()
        self.medium.setEditable(True)
        for key, label in MEDIUM_LABELS.items():
            self.medium.addItem(label, key)
        current = paint.medium if paint else medium
        index = self.medium.findData(current)
        if index < 0:
            self.medium.addItem(medium_label(current), current)
            index = self.medium.count() - 1
        self.medium.setCurrentIndex(index)
        self.medium.currentIndexChanged.connect(self._fill_stand_ins)
        form.addRow("Group", self.medium)

        self.brand = QLineEdit(paint.brand if paint else "")
        self.name = QLineEdit(paint.name if paint else "")
        self.code = QLineEdit(paint.code if paint else "")
        self.pigments = QLineEdit(", ".join(paint.pigments) if paint else "")
        self.pigments.setPlaceholderText("e.g. PB29, PW6")
        form.addRow("Brand", self.brand)
        form.addRow("Name", self.name)
        self.code.setToolTip("The maker's catalog number for the color, e.g. 036")
        self.series = QLineEdit(paint.series if paint else "")
        self.series.setToolTip("The maker's price series, e.g. A or 3")
        form.addRow("Code", self.code)
        form.addRow("Series", self.series)
        form.addRow("Pigments", self.pigments)

        self.opacity = QComboBox()
        self.opacity.addItem("—", "")
        for key, label in OPACITY_LABELS.items():
            self.opacity.addItem(label, key)
        self.opacity.setCurrentIndex(max(0, self.opacity.findData(paint.opacity if paint else "")))
        form.addRow("Opacity", self.opacity)
        self.drying = QLineEdit(paint.drying if paint else "")
        self.drying.setPlaceholderText("e.g. fast, medium, 3-5 days")
        form.addRow("Drying time", self.drying)

        color_row = QHBoxLayout()
        self.color_text = QLineEdit()
        self.color_text.setPlaceholderText("Paste the L*a*b* (D50) line, e.g. 13.26  22.45  -50.80")
        if paint and paint.lab:
            self.color_text.setText("{:.2f}  {:.2f}  {:.2f}".format(*paint.lab))
        self._initial_color_text = self.color_text.text()
        self.color_text.textChanged.connect(self._update_preview)
        self.chip = QLabel()
        self.chip.setFixedSize(QSize(40, 24))
        color_row.addWidget(self.color_text, 1)
        color_row.addWidget(self.chip)
        form.addRow("Color", color_row)
        self.color_note = QLabel()
        self.color_note.setWordWrap(True)
        self.color_note.setStyleSheet("color: gray;")
        form.addRow("", self.color_note)

        self.stand_in = QComboBox()
        form.addRow("Stand-in", self.stand_in)

        hint = QLabel("On a paint's artistpigments.org page, open <i>All color measurement details</i> and copy the "
                      "CIELAB D50 values. Leave Color empty to borrow a similar paint's color (stand-in).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)

        v = QVBoxLayout(self)
        v.addLayout(form)
        v.addWidget(hint)
        v.addWidget(buttons)
        self._fill_stand_ins()
        self._update_preview()

    # -- helpers -----------------------------------------------------------

    def _medium_key(self) -> str:
        text = self.medium.currentText().strip()
        index = self.medium.findText(text, Qt.MatchFixedString)
        return self.medium.itemData(index) if index >= 0 else (text.lower() or "oil")

    def _fill_stand_ins(self) -> None:
        keep = self.stand_in.currentData() if self.stand_in.count() else (self.paint.stand_in if self.paint else None)
        self.stand_in.blockSignals(True)
        self.stand_in.clear()
        probe = self._probe()
        auto = self.library.auto_stand_in(probe)
        self.stand_in.addItem(f"Automatic ({auto.name if auto else 'none found'})", None)
        self.stand_in.addItem("None", "")
        others = [p for p in self.library.paints if p.lab is not None and (self.paint is None or p.id != self.paint.id)]
        others.sort(key=lambda p: (p.medium != probe.medium, p.medium, p.name))
        for p in others:  # same group first; another group's paint can be chosen by hand
            group = "" if p.medium == probe.medium else f"  ({medium_label(p.medium)})"
            self.stand_in.addItem(f"{p.name} — {p.brand}{group}", p.id)
        index = self.stand_in.findData(keep)
        self.stand_in.setCurrentIndex(index if index >= 0 else 0)
        self.stand_in.blockSignals(False)

    def _probe(self) -> Paint:
        """A throwaway paint with the current entries, for stand-in lookups."""
        return Paint(id=self.paint.id if self.paint else "new", medium=self._medium_key(), brand=self.brand.text(),
                     name=self.name.text(), pigments=self._pigment_list())

    def _pigment_list(self) -> list[str]:
        return [p.strip().upper().replace("PBK", "PBk").replace("PBR", "PBr")
                for p in self.pigments.text().replace(";", ",").split(",") if p.strip()]

    def _update_preview(self) -> None:
        text = self.color_text.text()
        lab = parse_lab_text(text)
        self.stand_in.setEnabled(not text.strip())
        if lab is None:
            self.chip.setStyleSheet("border: 1px dashed #888;")
            self.color_note.setText("Can't read three numbers (L*, a*, b*) or a hex code from that."
                                    if text.strip() else "No color: the stand-in's color is used.")
            self.ok_button.setEnabled(not text.strip())
            return
        rgb, in_gamut = cs.lab_d50_to_srgb(lab)
        self.chip.setStyleSheet(chip_style(rgb))
        self.color_note.setText(f"L* {lab[0]:.2f}   a* {lab[1]:.2f}   b* {lab[2]:.2f}   screen {cs.hex_code(rgb)}"
                                + ("" if in_gamut else "\n" + OFF_SCREEN_NOTE))
        self.ok_button.setEnabled(True)

    def _accept(self) -> None:
        if not self.name.text().strip():
            self.name.setFocus()
            return
        self.accept()

    # -- result --------------------------------------------------------------

    def result_paint(self) -> Paint:
        """The edited paint (the same object when editing)."""
        p = self.paint or Paint(id=new_manual_id(), medium="", brand="", name="", source="Entered by hand")
        before = p.site_values()
        if self.color_text.text() != self._initial_color_text:  # the box shows 2 decimals; keep exact values
            lab = parse_lab_text(self.color_text.text())
            if lab is not None:
                p.source = "Entered by hand"
            p.lab = lab
        p.medium = self._medium_key()
        p.brand = self.brand.text().strip()
        p.name = self.name.text().strip()
        p.code = self.code.text().strip()
        p.series = self.series.text().strip()
        p.pigments = self._pigment_list()
        p.opacity = self.opacity.currentData()
        p.drying = self.drying.text().strip()
        p.stand_in = self.stand_in.currentData() if p.lab is None else None
        p.note_edits(before)
        return p
