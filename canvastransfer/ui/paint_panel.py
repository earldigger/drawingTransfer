"""Paints tab: the selected swatch matched to your paints, as single paints
(lightened with white or water) and two-paint mixes."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import color_study as cs
from ..mixing import WATER, MatchResult, Recipe, closeness, find_recipes
from ..paints import PaintLibrary, medium_label
from .paint_dialog import chip_style

ICON_SIZE = QSize(64, 40)
NO_LIGHTENER = "none"


def recipe_icon(target, recipe: Recipe) -> QIcon:
    """Target (left) next to the predicted mix (right), with the paints
    used as small chips along the bottom."""
    w, h = ICON_SIZE.width(), ICON_SIZE.height()
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.fillRect(QRectF(0, 0, w / 2, h - 10), QColor(*target))
    p.fillRect(QRectF(w / 2, 0, w / 2, h - 10), QColor(*recipe.rgb))
    chip_w = w / max(1, len(recipe.parts))
    for i, (paint, _share) in enumerate(recipe.parts):
        p.fillRect(QRectF(i * chip_w, h - 9, chip_w - 1, 9), QColor(*recipe.paint_rgbs[paint.id]))
    p.setPen(QPen(QColor(90, 90, 90), 1))
    p.drawRect(QRectF(0.5, 0.5, w - 1, h - 11))
    p.end()
    return QIcon(pm)


class PaintMatchPanel(QWidget):
    openLibraryRequested = Signal()

    def __init__(self, library: PaintLibrary, parent=None):
        super().__init__(parent)
        self.library = library
        self._target = None
        self._result: MatchResult | None = None
        self._dirty = True
        self._updating = False
        self._lightener_choice: dict[str, str] = {}  # medium -> what the user chose to lighten with

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QGroupBox("Match Swatch to Paints")
        tv = QVBoxLayout(top)
        row = QHBoxLayout()
        self.target_chip = QLabel()
        self.target_chip.setFixedSize(QSize(48, 32))
        self.target_label = QLabel()
        self.target_label.setWordWrap(True)
        row.addWidget(self.target_chip)
        row.addWidget(self.target_label, 1)
        tv.addLayout(row)
        form = QFormLayout()
        self.group = QComboBox()
        self.group.currentIndexChanged.connect(self._on_group_changed)
        form.addRow("Paints", self.group)
        self.lightener = QComboBox()
        self.lightener.setToolTip("What lightens the mixes: one of your whites, or water for watercolor")
        self.lightener.currentIndexChanged.connect(self._on_setting_changed)
        form.addRow("Lighten with", self.lightener)
        tv.addLayout(form)
        self.favorites_only = QCheckBox("Favorites only")
        self.favorites_only.toggled.connect(self._on_setting_changed)
        tv.addWidget(self.favorites_only)
        self.library_button = QPushButton("Paint Library…")
        self.library_button.clicked.connect(self.openLibraryRequested.emit)
        tv.addWidget(self.library_button, alignment=Qt.AlignRight)
        layout.addWidget(top)

        self.singles = self._result_list()
        self.pairs = self._result_list()
        for title, widget, tip in (
                ("One Paint", self.singles, "Each paint on its own, lightened as needed"),
                ("Two-Paint Mixes", self.pairs, "Two paints plus the lightener")):
            box = QGroupBox(title)
            box.setToolTip(tip)
            bv = QVBoxLayout(box)
            bv.addWidget(widget)
            layout.addWidget(box)

        self.note = QLabel(
            "Left: your swatch. Right: the predicted mix (Mixbox, the same model the artistpigments.org mixer "
            "uses). ΔE is the difference between them; under 2 is hard to see. Two paints plus white can match "
            "almost anything, so mixes within ΔE 1 are listed starting from paints already near your color. "
            "Mixbox treats every paint as "
            "equally strong, so trust which paints it names more than the amounts: phthalos and other strong "
            "pigments need much less than it says, earths more. ⚠ marks paints whose color is outside what a "
            "screen can show (clipped before mixing); * marks paints mixed with a stand-in's color.")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: gray;")
        layout.addWidget(self.note)
        layout.addStretch(1)
        self.reload_library()

    def _result_list(self) -> QListWidget:
        w = QListWidget()
        w.setIconSize(ICON_SIZE)
        w.setWordWrap(True)
        w.setMinimumHeight(5 * 48)
        w.setSelectionMode(QListWidget.NoSelection)
        return w

    # -- outward-facing API --------------------------------------------------

    def reload_library(self) -> None:
        """Refill the group and lightener choices after the library changed."""
        self._updating = True
        keep = self.group.currentData()
        self.group.clear()
        for medium in self.library.media():
            count = sum(1 for p in self.library.in_medium(medium) if self.library.color_of(p) is not None)
            self.group.addItem(f"{medium_label(medium)} ({count} with color)", medium)
        index = self.group.findData(keep)
        self.group.setCurrentIndex(index if index >= 0 else 0)
        self._fill_lighteners()
        self._updating = False
        self._dirty = True
        self._recompute()

    def set_target(self, rgb) -> None:
        self._target = tuple(rgb) if rgb is not None else None
        self._dirty = True
        self._recompute()

    def result(self) -> MatchResult | None:
        return self._result

    # -- internals ---------------------------------------------------------

    def _fill_lighteners(self) -> None:
        medium = self.group.currentData()
        keep = self._lightener_choice.get(medium)
        self.lightener.blockSignals(True)
        self.lightener.clear()
        whites = [p for p in self.library.in_medium(medium or "") if p.is_white and self.library.color_of(p)]
        whites.sort(key=lambda p: (not p.favorite, "titanium" not in p.name.lower(), p.name))
        for p in whites:
            self.lightener.addItem(f"{p.name} — {p.brand}", p.id)
        self.lightener.addItem("Water (paper white)", WATER.id)
        self.lightener.addItem("Nothing", NO_LIGHTENER)
        index = self.lightener.findData(keep)
        if index < 0:
            index = self.lightener.findData(WATER.id) if medium == "watercolor" or not whites else 0
        self.lightener.setCurrentIndex(index)
        self.lightener.blockSignals(False)

    def _on_group_changed(self, _index) -> None:
        if self._updating:
            return
        self._fill_lighteners()
        self._on_setting_changed()

    def _on_setting_changed(self, *_args) -> None:
        if self._updating:
            return
        if self.lightener.count():
            self._lightener_choice[self.group.currentData()] = self.lightener.currentData()
        self._dirty = True
        self._recompute()

    def showEvent(self, event):
        super().showEvent(event)
        self._recompute()

    def _recompute(self) -> None:
        if not self._dirty or not self.isVisible():
            return  # done when the tab is shown
        self._dirty = False
        self._result = None
        self.singles.clear()
        self.pairs.clear()
        rgb = self._target
        if rgb is None:
            self.target_chip.setStyleSheet("border: 1px dashed #888;")
            self.target_label.setText("Select a swatch on the Color Study tab.")
            return
        self.target_chip.setStyleSheet(chip_style(rgb))
        self.target_label.setText(f"<b>{cs.hex_code(rgb)}</b>  RGB {rgb[0]}, {rgb[1]}, {rgb[2]}")
        medium = self.group.currentData()
        if medium is None:
            self.target_label.setText(self.target_label.text() + "<br>Your paint library is empty: open the "
                                      "Paint Library and import your saved collection page.")
            return
        paints = [p for p in self.library.in_medium(medium)
                  if p.enabled and (p.favorite or not self.favorites_only.isChecked())]
        choice = self.lightener.currentData()
        lightener = WATER if choice == WATER.id else (None if choice == NO_LIGHTENER else self.library.get(choice))
        self._result = find_recipes(rgb, self.library, paints, lightener)
        self._show(self.singles, self._result.singles)
        self._show(self.pairs, self._result.pairs)

    def _show(self, widget: QListWidget, recipes: list[Recipe]) -> None:
        if not recipes:
            item = QListWidgetItem("No paints with color data in this group.")
            widget.addItem(item)
            return
        for r in recipes:
            off = {p.id for p in r.off_screen}
            borrowed = {p.id for p in r.stand_ins}
            lines = []
            for paint, share in r.parts:
                mark = ("⚠" if paint.id in off else "") + ("*" if paint.id in borrowed else "")
                alt = r.also.get(paint.id, [])
                alt_text = f"  (or {', '.join(a.name + ('*' if a.lab is None else '') for a in alt)})" if alt else ""
                lines.append(f"{round(share * 100)}%  {paint.name}{mark}{alt_text}")
            text = f"ΔE {r.delta_e:.1f} — {closeness(r.delta_e)}\n" + "\n".join(lines)
            item = QListWidgetItem(recipe_icon(self._target, r), text)
            tip = [f"Predicted mix {cs.hex_code(r.rgb)}"]
            for paint, _share in r.parts:
                tip.append(f"{paint.label()}" + (f" — also: {'; '.join(a.label() for a in r.also[paint.id])}"
                                                  if paint.id in r.also else ""))
            item.setToolTip("\n".join(tip))
            widget.addItem(item)
