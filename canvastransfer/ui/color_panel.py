"""Color Study panel: sample size, simplify, swatch list with highlight
checkboxes (each in its own color), highlight tolerance, and details for the
selected swatch."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QLinearGradient, QPainter, QPen, QPixmap
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
from ..models import Project, SimplifySettings
from .slider_row import ValueSliderRow

SWATCH_ID_ROLE = Qt.UserRole + 1
SAMPLE_SIZES = [("Point (1 px)", 0), ("5 x 5 px", 2), ("11 x 11 px", 5), ("21 x 21 px", 10), ("41 x 41 px", 20)]
DEFAULT_SAMPLE_INDEX = 2


def _text_color(rgb) -> QColor:
    return QColor(Qt.black) if 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2] > 150 else QColor(Qt.white)


def swatch_icon(rgb, number: int, size: int = 28, ring=None) -> QIcon:
    """The swatch color with its number; `ring` (its highlight color) is
    drawn as a thick border while the swatch is highlighted."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if ring is not None:
        p.setBrush(QColor(*ring))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, size, size), 6, 6)
        inset = 4
    else:
        inset = 1
    p.setBrush(QColor(*rgb))
    p.setPen(QPen(QColor(90, 90, 90), 1))
    p.drawRoundedRect(QRectF(inset, inset, size - 2 * inset, size - 2 * inset), 4, 4)
    p.setPen(_text_color(rgb))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(12)
    p.setFont(f)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, str(number))
    p.end()
    return QIcon(pm)


class ColorStrip(QWidget):
    """A row of color boxes (tints, shades, tones, complement)."""

    def __init__(self, height: int = 26, parent=None):
        super().__init__(parent)
        self._colors: list[tuple[int, int, int]] = []
        self._weights: list[float] | None = None
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)

    def set_colors(self, colors, weights=None) -> None:
        """Equal boxes, or boxes as wide as `weights` (e.g. area shares)."""
        self._colors = list(colors)
        self._weights = list(weights) if weights else None
        tips = [cs.hex_code(c) + (f" {w:.0%}" if self._weights else "")
                for c, w in zip(self._colors, self._weights or [None] * len(self._colors))]
        self.setToolTip("  ".join(tips))
        self.update()

    def colors(self):
        return list(self._colors)

    def paintEvent(self, event):
        if not self._colors:
            return
        p = QPainter(self)
        weights = self._weights or [1.0] * len(self._colors)
        total = sum(weights) or 1.0
        x = 0.0
        for c, wt in zip(self._colors, weights):
            w = self.width() * wt / total
            p.fillRect(QRectF(x, 0, w + 0.5, self.height()), QColor(*c))
            x += w
        p.setPen(QPen(QColor(90, 90, 90), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1))
        p.end()


class ScaleBar(QWidget):
    """A value scale (stepped grays 0..10) or a cool-to-warm gradient, with
    a marker showing where the selected color sits."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self._kind = kind  # "value" or "temperature"
        self._position: float | None = None  # 0..1
        self._marker_rgb = (128, 128, 128)
        self.setMinimumHeight(24)
        self.setMaximumHeight(24)

    def set_marker(self, position: float | None, rgb=(128, 128, 128)) -> None:
        self._position = position
        self._marker_rgb = rgb
        self.update()

    def position(self) -> float | None:
        return self._position

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if self._kind == "value":
            for i in range(11):  # Munsell value steps 0..10
                g = round(255 * (i / 10) ** 1.2)
                p.fillRect(QRectF(i * w / 11, 0, w / 11 + 0.5, h), QColor(g, g, g))
            x = (self._position or 0) * (w - w / 11) + w / 22
        else:
            grad = QLinearGradient(0, 0, w, 0)
            grad.setColorAt(0.0, QColor(110, 180, 240))
            grad.setColorAt(0.5, QColor(225, 225, 225))
            grad.setColorAt(1.0, QColor(240, 180, 90))
            p.fillRect(QRectF(0, 4, w, h - 8), grad)
            x = (self._position or 0) * w
        if self._position is not None:
            x = min(max(x, 7), w - 7)
            p.setPen(QPen(Qt.white, 2))
            p.setBrush(QColor(*self._marker_rgb))
            p.drawEllipse(QPointF(x, h / 2), 7, 7)
        p.end()


class ColorStudyPanel(QWidget):
    swatchSelected = Signal(str)
    swatchRemoveRequested = Signal(str)
    swatchHighlightToggled = Signal(str, bool)
    toleranceChanged = Signal(float)
    sampleSizeChanged = Signal(int)
    simplifyChanged = Signal(object)  # SimplifySettings
    addSimplifiedSwatchesRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._selected_rgb: tuple[int, int, int] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_pick_box())
        layout.addWidget(self._build_simplify_box())
        layout.addWidget(self._build_swatch_box())
        layout.addWidget(self._build_details_box())
        layout.addStretch(1)
        self.show_details(None)

    # -- construction -----------------------------------------------------

    def _build_pick_box(self) -> QGroupBox:
        box = QGroupBox("Pick Colors")
        v = QVBoxLayout(box)
        hint = QLabel("Turn on <b>Pick Color</b> (I) in the toolbar, then click the selected layer "
                      "to add a swatch. Clicking a numbered marker selects its swatch.")
        hint.setWordWrap(True)
        v.addWidget(hint)
        row = QHBoxLayout()
        row.addWidget(QLabel("Sample size"))
        self.sample_size = QComboBox()
        for label, radius in SAMPLE_SIZES:
            self.sample_size.addItem(label, radius)
        self.sample_size.setCurrentIndex(DEFAULT_SAMPLE_INDEX)
        self.sample_size.setToolTip("Averages the pixels in this area, so film grain and noise don't skew the color")
        self.sample_size.currentIndexChanged.connect(lambda _: self.sampleSizeChanged.emit(self.sample_radius()))
        row.addWidget(self.sample_size, 1)
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Under cursor"))
        self.hover_chip = QLabel()
        self.hover_chip.setFixedSize(QSize(28, 20))
        self.hover_text = QLabel("—")
        row.addWidget(self.hover_chip)
        row.addWidget(self.hover_text, 1)
        v.addLayout(row)
        return box

    def _build_simplify_box(self) -> QGroupBox:
        box = QGroupBox("Simplify")
        v = QVBoxLayout(box)
        self.simplify_check = QCheckBox("Simplify the selected layer")
        self.simplify_check.setToolTip("Show the layer as a few flat colors (or gray values), to see its big shapes")
        self.simplify_check.toggled.connect(self._emit_simplify_now)
        v.addWidget(self.simplify_check)
        row = QHBoxLayout()
        row.addWidget(QLabel("Show"))
        self.simplify_mode = QComboBox()
        self.simplify_mode.addItem("Colors", False)
        self.simplify_mode.addItem("Values (grays)", True)
        self.simplify_mode.currentIndexChanged.connect(self._on_simplify_mode)
        row.addWidget(self.simplify_mode, 1)
        v.addLayout(row)
        self.simplify_count = ValueSliderRow(v, "Colors", 2, 24, 8, ["#6b8fbf", "#e0a060", "#c04060"],
                                             "How many flat colors (or values) the layer is reduced to")
        self.simplify_smoothing = ValueSliderRow(v, "Smoothing", 0, 6, 2, ["#3a3a3a", "#e8e8e8"],
                                                 "Flattens texture and removes specks, for simpler shapes")
        self._simplify_timer = QTimer(self)  # wait for a pause in dragging: each update takes a moment
        self._simplify_timer.setSingleShot(True)
        self._simplify_timer.setInterval(180)
        self._simplify_timer.timeout.connect(self._emit_simplify_now)
        for row_ in (self.simplify_count, self.simplify_smoothing):
            row_.slider.valueChanged.connect(self._on_simplify_slider)
        self.simplify_palette = ColorStrip(22)
        self.simplify_palette.setToolTip("The simplified colors, as wide as the area they cover")
        v.addWidget(self.simplify_palette)
        self.simplify_add = QPushButton("Add Colors as Swatches")
        self.simplify_add.setToolTip("One swatch per simplified color, placed inside its largest area")
        self.simplify_add.clicked.connect(self.addSimplifiedSwatchesRequested.emit)
        v.addWidget(self.simplify_add, alignment=Qt.AlignRight)
        note = QLabel("While this is on, picking and highlights use the simplified colors.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        v.addWidget(note)
        self._simplify = SimplifySettings()
        self._update_simplify_widgets()
        return box

    def _build_swatch_box(self) -> QGroupBox:
        box = QGroupBox("Swatches")
        v = QVBoxLayout(box)
        note = QLabel("Tick a swatch to highlight similar colors on its layer.")
        note.setWordWrap(True)
        v.addWidget(note)
        self.swatch_list = QListWidget()
        self.swatch_list.setIconSize(QSize(28, 28))
        self.swatch_list.setMinimumHeight(150)
        self.swatch_list.currentItemChanged.connect(self._on_current_changed)
        self.swatch_list.itemChanged.connect(self._on_item_changed)
        v.addWidget(self.swatch_list)
        self.remove_button = QPushButton("Remove Swatch")
        self.remove_button.clicked.connect(self._emit_remove)
        v.addWidget(self.remove_button, alignment=Qt.AlignRight)
        self.tolerance = ValueSliderRow(v, "Highlight tolerance", 1, 40, 12, ["#3a3a3a", "#e8e8e8"],
                                        "How different a color can be and still count as similar "
                                        "(CIELAB distance; about 2 is a just-visible difference)")
        self.tolerance.slider.valueChanged.connect(self._on_tolerance_changed)
        return box

    def _build_details_box(self) -> QGroupBox:
        box = QGroupBox("Swatch Details")
        v = QVBoxLayout(box)
        top = QHBoxLayout()
        self.detail_chip = QLabel()
        self.detail_chip.setFixedSize(QSize(64, 64))
        top.addWidget(self.detail_chip)
        info = QVBoxLayout()
        self.hex_label = QLabel()
        f = self.hex_label.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 3)
        self.hex_label.setFont(f)
        self.hex_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.rgb_label = QLabel()
        self.rgb_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info.addWidget(self.hex_label)
        info.addWidget(self.rgb_label)
        top.addLayout(info, 1)
        self.copy_button = QPushButton("Copy Hex")
        self.copy_button.clicked.connect(self._copy_hex)
        top.addWidget(self.copy_button, alignment=Qt.AlignTop)
        v.addLayout(top)

        form = QFormLayout()
        self.lab_label = QLabel()
        self.lab_label.setToolTip("CIELAB under D50, the convention artistpigments.org lists paints in")
        self.lab_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.munsell_label = QLabel()
        self.munsell_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.munsell_label.setWordWrap(True)
        form.addRow("L*a*b* (D50)", self.lab_label)
        form.addRow("Munsell", self.munsell_label)
        v.addLayout(form)

        self.value_label = QLabel()
        v.addWidget(self.value_label)
        self.value_bar = ScaleBar("value")
        v.addWidget(self.value_bar)
        self.temperature_label = QLabel()
        self.temperature_label.setToolTip("A rule of thumb from hue and chroma; there is no standard warm/cool scale")
        v.addWidget(self.temperature_label)
        self.temperature_bar = ScaleBar("temperature")
        v.addWidget(self.temperature_bar)

        self.tints = ColorStrip()
        self.shades = ColorStrip()
        self.tones = ColorStrip()
        self.complement = ColorStrip()
        for title, strip in (("Tints  + white", self.tints), ("Shades  + black", self.shades),
                             ("Tones  + gray", self.tones), ("Complementary", self.complement)):
            v.addWidget(QLabel(title))
            v.addWidget(strip)
        mix_note = QLabel("Tints, shades and tones are mixed like pigment (Mixbox), so yellow + black "
                          "goes olive as real paint does.")
        mix_note.setWordWrap(True)
        mix_note.setStyleSheet("color: gray;")
        v.addWidget(mix_note)
        self._detail_widgets = [self.copy_button]
        return box

    # -- outward-facing API ------------------------------------------------

    def set_simplify(self, settings: SimplifySettings) -> None:
        """Show a project's simplify settings without emitting changes."""
        self._simplify = SimplifySettings.from_dict(settings.to_dict())
        self._updating = True
        self.simplify_check.setChecked(settings.enabled)
        self.simplify_mode.setCurrentIndex(1 if settings.values else 0)
        self._update_simplify_widgets()
        self._updating = False

    def show_simplified(self, colors, shares) -> None:
        self.simplify_palette.set_colors(colors, shares)
        self.simplify_add.setEnabled(bool(colors))

    def _update_simplify_widgets(self) -> None:
        st = self._simplify
        was = self._updating
        self._updating = True
        self.simplify_count.label.setText("Values:" if st.values else "Colors:")
        self.simplify_count.set_range(2, 10 if st.values else 24)
        self.simplify_count.set(st.value_steps if st.values else st.colors)
        self.simplify_smoothing.set(st.smoothing)
        self._updating = was
        for w in (self.simplify_mode, *self.simplify_count.widgets(), *self.simplify_smoothing.widgets()):
            w.setEnabled(st.enabled)
        if not st.enabled:
            self.show_simplified([], [])

    def _on_simplify_mode(self, _index) -> None:
        if self._updating:
            return
        self._simplify.values = bool(self.simplify_mode.currentData())
        self._update_simplify_widgets()
        self._emit_simplify_now()

    def _on_simplify_slider(self, _value) -> None:
        if self._updating:
            return
        self._read_simplify_sliders()
        self._simplify_timer.start()

    def _read_simplify_sliders(self) -> None:
        st = self._simplify
        if st.values:
            st.value_steps = self.simplify_count.slider.value()
        else:
            st.colors = self.simplify_count.slider.value()
        st.smoothing = self.simplify_smoothing.slider.value()

    def _emit_simplify_now(self, *_args) -> None:
        if self._updating:
            return
        self._simplify_timer.stop()
        self._simplify.enabled = self.simplify_check.isChecked()
        self._read_simplify_sliders()
        self._update_simplify_widgets()
        self.simplifyChanged.emit(SimplifySettings.from_dict(self._simplify.to_dict()))

    def sample_radius(self) -> int:
        return int(self.sample_size.currentData())

    def refresh(self, project: Project, selected_id: str | None) -> None:
        self._updating = True
        self.swatch_list.clear()
        for number, swatch in enumerate(project.swatches, start=1):
            ring = cs.highlight_color(number - 1) if swatch.highlight else None
            item = QListWidgetItem(swatch_icon(swatch.rgb, number, ring=ring), f"{cs.hex_code(swatch.rgb)}   RGB {swatch.rgb[0]}, {swatch.rgb[1]}, {swatch.rgb[2]}")
            item.setData(SWATCH_ID_ROLE, swatch.id)
            item.setFlags((item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            item.setCheckState(Qt.Checked if swatch.highlight else Qt.Unchecked)
            item.setToolTip("Tick to highlight similar colors; each swatch highlights in its own color "
                            "(shown as the border)")
            self.swatch_list.addItem(item)
            if swatch.id == selected_id:
                self.swatch_list.setCurrentItem(item)
        self.tolerance.set(round(project.highlight_tolerance))
        self.remove_button.setEnabled(project.get_swatch(selected_id) is not None)
        self._updating = False
        selected = project.get_swatch(selected_id)
        self.show_details(selected.rgb if selected else None)

    def show_hover(self, rgb) -> None:
        if rgb is None:
            self.hover_chip.setStyleSheet("")
            self.hover_text.setText("—")
            return
        self.hover_chip.setStyleSheet(f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]}); border: 1px solid #666;")
        self.hover_text.setText(f"{cs.hex_code(rgb)}   RGB {rgb[0]}, {rgb[1]}, {rgb[2]}")

    def show_details(self, rgb) -> None:
        self._selected_rgb = rgb
        for w in self._detail_widgets:
            w.setEnabled(rgb is not None)
        if rgb is None:
            self.detail_chip.setStyleSheet("border: 1px dashed #888;")
            self.hex_label.setText("No swatch selected")
            for label in (self.rgb_label, self.lab_label, self.munsell_label, self.value_label, self.temperature_label):
                label.setText("")
            self.value_bar.set_marker(None)
            self.temperature_bar.set_marker(None)
            for strip in (self.tints, self.shades, self.tones, self.complement):
                strip.set_colors([])
            return
        self.detail_chip.setStyleSheet(f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]}); border: 1px solid #666; border-radius: 6px;")
        self.hex_label.setText(cs.hex_code(rgb))
        self.rgb_label.setText(f"RGB {rgb[0]}, {rgb[1]}, {rgb[2]}")
        L, a, b = cs.lab_d50(rgb)
        self.lab_label.setText(f"L* {L:.1f}   a* {a:.1f}   b* {b:.1f}")
        notation, value = cs.munsell(rgb)
        self.munsell_label.setText(notation or f"value {value:.1f} (hue/chroma outside the Munsell data)")
        self.value_label.setText(f"<b>Value {round(value)}/10</b>  ({value:.1f})")
        self.value_bar.set_marker(min(max(value / 10, 0), 1), rgb)
        score, label = cs.temperature(rgb)
        self.temperature_label.setText(f"<b>{label}</b>  (cool ← → warm)")
        self.temperature_bar.set_marker((score + 1) / 2, rgb)
        self.tints.set_colors(cs.tints(rgb))
        self.shades.set_colors(cs.shades(rgb))
        self.tones.set_colors(cs.tones(rgb))
        self.complement.set_colors([rgb, cs.complement(rgb)])

    # -- internal handlers ---------------------------------------------

    def _current_id(self) -> str | None:
        item = self.swatch_list.currentItem()
        return item.data(SWATCH_ID_ROLE) if item else None

    def _on_current_changed(self, current, _previous):
        if self._updating or current is None:
            return
        self.swatchSelected.emit(current.data(SWATCH_ID_ROLE))

    def _on_item_changed(self, item: QListWidgetItem):
        if self._updating:
            return
        # emitted after Qt has finished with this click: the handler rebuilds the
        # list, which would otherwise delete the item while its signal is running
        item_id, on = item.data(SWATCH_ID_ROLE), item.checkState() == Qt.Checked
        QTimer.singleShot(0, lambda: self.swatchHighlightToggled.emit(item_id, on))

    def _emit_remove(self):
        swatch_id = self._current_id()
        if swatch_id:
            self.swatchRemoveRequested.emit(swatch_id)

    def _on_tolerance_changed(self, value: int):
        if not self._updating:
            self.toleranceChanged.emit(float(value))

    def _copy_hex(self):
        if self._selected_rgb is not None:
            QGuiApplication.clipboard().setText(cs.hex_code(self._selected_rgb))
