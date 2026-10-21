"""Create or edit a limited palette: a name, a medium, and the paints in it."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from .. import color_study as cs
from ..paints import Palette, PaintLibrary, medium_label, new_palette_id
from .paint_dialog import paint_chip

PAINT_ID_ROLE = Qt.UserRole + 1


class PaletteDialog(QDialog):
    def __init__(self, library: PaintLibrary, palette: Palette | None = None, medium: str = "oil", parent=None):
        super().__init__(parent)
        self.library = library
        self.palette = palette
        self._checked: set[str] = set(palette.paint_ids) if palette else set()
        self.setWindowTitle("Edit Palette" if palette else "New Palette")
        self.resize(520, 640)

        form = QFormLayout()
        self.name = QLineEdit(palette.name if palette else "")
        self.name.setPlaceholderText("e.g. My portrait palette")
        self.name.textChanged.connect(self._update_ok)
        form.addRow("Name", self.name)
        self.medium = QComboBox()
        for m in library.media() or ["oil"]:
            self.medium.addItem(medium_label(m), m)
        self.medium.setCurrentIndex(max(0, self.medium.findData(palette.medium if palette else medium)))
        self.medium.currentIndexChanged.connect(self._fill)
        form.addRow("Group", self.medium)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by name, brand or pigment")
        self.filter.textChanged.connect(self._apply_filter)
        form.addRow("Find", self.filter)

        self.list = QListWidget()
        self.list.itemChanged.connect(self._on_item_changed)
        self.count = QLabel()
        self.count.setStyleSheet("color: gray;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)

        v = QVBoxLayout(self)
        v.addLayout(form)
        v.addWidget(QLabel("Tick the paints in this palette:"))
        v.addWidget(self.list, 1)
        v.addWidget(self.count)
        v.addWidget(buttons)
        self._fill()

    def _fill(self, *_args) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        medium = self.medium.currentData()
        paints = sorted(self.library.in_medium(medium), key=lambda p: (not p.favorite, p.name.lower(), p.brand.lower()))
        for p in paints:
            lab = self.library.color_of(p)
            note = "" if lab is not None else "   (no color data)"
            item = QListWidgetItem(paint_chip(cs.lab_d50_to_srgb(lab)[0] if lab else None, dashed=p.lab is None),
                                   f"{p.name} — {p.brand}{note}")
            item.setData(PAINT_ID_ROLE, p.id)
            item.setToolTip(f"{p.label()}\nPigments: {', '.join(p.pigments) or '—'}")
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if p.id in self._checked else Qt.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._apply_filter()
        self._update_ok()

    def _apply_filter(self, *_args) -> None:
        words = self.filter.text().lower().split()
        for i in range(self.list.count()):
            item = self.list.item(i)
            haystack = (item.text() + " " + item.toolTip()).lower()
            item.setHidden(not all(w in haystack for w in words))

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        pid = item.data(PAINT_ID_ROLE)
        if item.checkState() == Qt.Checked:
            self._checked.add(pid)
        else:
            self._checked.discard(pid)
        self._update_ok()

    def check(self, paint_id: str, on: bool = True) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(PAINT_ID_ROLE) == paint_id:
                item.setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _ids_in_medium(self) -> list[str]:
        return [self.list.item(i).data(PAINT_ID_ROLE) for i in range(self.list.count())
                if self.list.item(i).data(PAINT_ID_ROLE) in self._checked]

    def _update_ok(self, *_args) -> None:
        n = len(self._ids_in_medium())
        self.count.setText(f"{n} paints selected")
        self.ok_button.setEnabled(bool(self.name.text().strip()) and n > 0)

    def result_palette(self) -> Palette:
        """The edited palette (the same object when editing)."""
        p = self.palette or Palette(id=new_palette_id(), name="", medium="")
        p.name = self.name.text().strip()
        p.medium = self.medium.currentData()
        p.paint_ids = self._ids_in_medium()
        return p
