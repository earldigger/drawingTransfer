"""Paints tab: the selected swatch matched to your paints, as single paints
(lightened with white or water) and two-paint mixes. Mix from a whole
paint group, one of your palettes, or a classic limited palette."""

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
from .. import palettes
from ..mixing import (MIXBOX, MODELS, WATER, MatchResult, MixModel, Recipe, closeness, find_recipes, percent,
                      predict)
from ..paints import Paint, PaintLibrary, medium_label
from .paint_dialog import chip_style

ICON_SIZE = QSize(64, 40)
NO_LIGHTENER = "none"


def recipe_icon(target, recipe: Recipe, other_rgb=None) -> QIcon:
    """Target (left) next to the predicted mix (right), with the paints
    used as small chips along the bottom. With `other_rgb`, the other
    mixing model's prediction for the same amounts is a strip on the right."""
    w, h = ICON_SIZE.width(), ICON_SIZE.height()
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.fillRect(QRectF(0, 0, w / 2, h - 10), QColor(*target))
    p.fillRect(QRectF(w / 2, 0, w / 2, h - 10), QColor(*recipe.rgb))
    if other_rgb is not None:
        p.fillRect(QRectF(w - 10, 0, 10, h - 10), QColor(*other_rgb))
    chip_w = w / max(1, len(recipe.parts))
    for i, (paint, _share) in enumerate(recipe.parts):
        p.fillRect(QRectF(i * chip_w, h - 9, chip_w - 1, 9), QColor(*recipe.paint_rgbs[paint.id]))
    p.setPen(QPen(QColor(90, 90, 90), 1))
    p.drawRect(QRectF(0.5, 0.5, w - 1, h - 11))
    p.end()
    return QIcon(pm)


class PaintMatchPanel(QWidget):
    openLibraryRequested = Signal()
    openPalettesRequested = Signal()

    def __init__(self, library: PaintLibrary, parent=None):
        super().__init__(parent)
        self.library = library
        self._target = None
        self._result: MatchResult | None = None
        self._dirty = True
        self._updating = False
        self._lightener_choice: dict[str, str] = {}  # "Mix from" choice -> what the user chose to lighten with

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
        self.group.setToolTip("Mix from all your paints in a group, one of your palettes, or a classic palette")
        self.group.currentIndexChanged.connect(self._on_group_changed)
        form.addRow("Mix from", self.group)
        self.lightener = QComboBox()
        self.lightener.setToolTip("What lightens the mixes: one of your whites, or water for watercolor")
        self.lightener.currentIndexChanged.connect(self._on_setting_changed)
        form.addRow("Lighten with", self.lightener)
        self.model = QComboBox()
        for m in MODELS:
            self.model.addItem(m.name, m.id)
        self.model.setToolTip("How mixes are predicted. Each recipe also shows what the other model says the "
                              "same amounts make (the strip on the right of its swatch).")
        self.model.currentIndexChanged.connect(self._on_setting_changed)
        form.addRow("Mixing", self.model)
        tv.addLayout(form)
        self.palette_label = QLabel()
        self.palette_label.setWordWrap(True)
        self.palette_label.setStyleSheet("color: gray;")
        tv.addWidget(self.palette_label)
        self.favorites_only = QCheckBox("Favorites only")
        self.favorites_only.toggled.connect(self._on_setting_changed)
        tv.addWidget(self.favorites_only)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.palettes_button = QPushButton("Palettes…")
        self.palettes_button.clicked.connect(self.openPalettesRequested.emit)
        self.library_button = QPushButton("Paint Library…")
        self.library_button.clicked.connect(self.openLibraryRequested.emit)
        buttons.addWidget(self.palettes_button)
        buttons.addWidget(self.library_button)
        tv.addLayout(buttons)
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
            "Left: your swatch. Right: the predicted mix; the strip at the far right is what the other mixing "
            "model predicts for the same amounts. Mixbox is the model the artistpigments.org mixer uses; "
            "Kubelka-Munk is the published paint physics, run on a smooth spectrum guessed from each paint's "
            "color. ΔE is the difference from your swatch; under 2 is hard to see. Two paints plus white can "
            "match almost anything, so mixes within ΔE 1 are listed starting from paints already near your "
            "color. Both models treat every paint as "
            "equally strong unless you set its Strength in Edit Paint, so without it trust which paints they "
            "name more than the amounts: phthalos and other strong "
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
        """Refill the Mix from and lightener choices after the library changed."""
        self._updating = True
        keep = self.group.currentData()
        self.group.clear()
        media = self.library.media()
        for medium in media:
            count = sum(1 for p in self.library.in_medium(medium) if self.library.color_of(p) is not None)
            self.group.addItem(f"All {medium_label(medium).lower()} paints ({count} with color)", f"medium:{medium}")
        if self.library.palettes:
            self.group.insertSeparator(self.group.count())
            for p in self.library.palettes:
                self.group.addItem(f"{p.name}  ({medium_label(p.medium).lower()}, {len(p.paint_ids)})",
                                   f"palette:{p.id}")
        classics = [(t, m) for m in media for t in palettes.TEMPLATES
                    if sum(f.paint is not None for f in palettes.fill(t, self.library, m).roles) >= 2]
        if classics:
            self.group.insertSeparator(self.group.count())
            for t, m in classics:
                self.group.addItem(f"{t.name}  (classic, {medium_label(m).lower()})", f"template:{t.key}:{m}")
        index = self.group.findData(keep) if keep else -1  # separators have no data
        self.group.setCurrentIndex(index if index >= 0 else 0)
        self._fill_lighteners()
        self._describe_selection()
        self._updating = False
        self._dirty = True
        self._recompute()

    def set_target(self, rgb) -> None:
        self._target = tuple(rgb) if rgb is not None else None
        self._dirty = True
        self._recompute()

    def result(self) -> MatchResult | None:
        return self._result

    def mix_model(self) -> MixModel:
        return next((m for m in MODELS if m.id == self.model.currentData()), MIXBOX)

    def other_model(self) -> MixModel:
        return next(m for m in MODELS if m is not self.mix_model())

    def select_source(self, key: str) -> None:
        """Choose what to mix from by its key, e.g. "medium:oil", "palette:<id>"
        or "template:zorn:oil"."""
        index = self.group.findData(key)
        if index >= 0:
            self.group.setCurrentIndex(index)

    def selection(self) -> tuple[str | None, list[Paint], str]:
        """(medium, paints to mix from, description) for the Mix from choice."""
        key = self.group.currentData() or ""
        kind, _, rest = key.partition(":")
        if kind == "medium":
            paints = [p for p in self.library.in_medium(rest)
                      if p.enabled and (p.favorite or not self.favorites_only.isChecked())]
            return rest, paints, ""
        if kind == "palette":
            palette = self.library.get_palette(rest)
            if palette is None:
                return None, [], ""
            paints = self.library.palette_paints(palette)
            missing = [p.name for p in paints if self.library.color_of(p) is None]
            text = ", ".join(p.name for p in paints)
            if missing:
                text += f".  No color data (left out): {', '.join(missing)}"
            return palette.medium, paints, text
        if kind == "template":
            key_, _, medium = rest.partition(":")
            filled = palettes.fill(palettes.template(key_), self.library, medium)
            parts = [f"{f.paint.name}{' (for ' + f.role.name.lower() + ')' if f.substitute else ''}"
                     for f in filled.roles if f.paint is not None]
            text = ", ".join(parts)
            empty = [f.role.name.lower() for f in filled.roles if f.paint is None]
            if empty:
                text += f".  None of your paints fits: {', '.join(empty)}"
            return medium, filled.paints(), text
        return None, [], ""

    # -- internals ---------------------------------------------------------

    def _fill_lighteners(self) -> None:
        """Whites of the group, water and nothing. A palette's own white is
        chosen first, then the last choice for this Mix from entry."""
        medium, selected, _ = self.selection()
        keep = self._lightener_choice.get(self.group.currentData())
        self.lightener.blockSignals(True)
        self.lightener.clear()
        whites = [p for p in self.library.in_medium(medium or "") if p.is_white and self.library.color_of(p)]
        in_selection = {p.id for p in selected}
        whites.sort(key=lambda p: (p.id not in in_selection, not p.favorite, "titanium" not in p.name.lower(), p.name))
        for p in whites:
            self.lightener.addItem(f"{p.name} — {p.brand}", p.id)
        self.lightener.addItem("Water (paper white)", WATER.id)
        self.lightener.addItem("Nothing", NO_LIGHTENER)
        index = self.lightener.findData(keep)
        if index < 0:
            index = self.lightener.findData(WATER.id) if medium == "watercolor" or not whites else 0
        self.lightener.setCurrentIndex(index)
        self.lightener.blockSignals(False)

    def _describe_selection(self) -> None:
        kind = (self.group.currentData() or "").partition(":")[0]
        _, _, text = self.selection()
        if kind == "template":
            name = self.group.currentData().split(":")[1]
            self.palette_label.setToolTip(palettes.template(name).note)
        else:
            self.palette_label.setToolTip("")
        self.palette_label.setText(text)
        self.palette_label.setVisible(bool(text))
        self.favorites_only.setEnabled(kind == "medium")

    def _on_group_changed(self, _index) -> None:
        if self._updating:
            return
        self._fill_lighteners()
        self._describe_selection()
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
        if self.group.currentData() is None:
            self.target_label.setText(self.target_label.text() + "<br>Your paint library is empty: open the "
                                      "Paint Library and import your saved collection page.")
            return
        _, paints, _ = self.selection()
        choice = self.lightener.currentData()
        lightener = WATER if choice == WATER.id else (None if choice == NO_LIGHTENER else self.library.get(choice))
        self._result = find_recipes(rgb, self.library, paints, lightener, self.mix_model())
        self._show(self.singles, self._result.singles)
        self._show(self.pairs, self._result.pairs)

    def _show(self, widget: QListWidget, recipes: list[Recipe]) -> None:
        if not recipes:
            item = QListWidgetItem("No paints with color data to mix from.")
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
                strength = f"  (strength ×{paint.strength:g})" if paint.strength != 1 else ""
                lines.append(f"{percent(share)}  {paint.name}{mark}{strength}{alt_text}")
            other = self.other_model()
            other_rgb, other_de = predict(r, self._target, other)
            text = (f"ΔE {r.delta_e:.1f} — {closeness(r.delta_e)}\n" + "\n".join(lines)
                    + f"\n{other.name}: ΔE {other_de:.1f} for these amounts")
            item = QListWidgetItem(recipe_icon(self._target, r, other_rgb), text)
            tip = [f"Predicted mix {cs.hex_code(r.rgb)} ({self.mix_model().name}); "
                   f"{other.name} predicts {cs.hex_code(other_rgb)}"]
            for paint, _share in r.parts:
                tip.append(f"{paint.label()}" + (f" — also: {'; '.join(a.label() for a in r.also[paint.id])}"
                                                  if paint.id in r.also else ""))
            item.setToolTip("\n".join(tip))
            widget.addItem(item)
