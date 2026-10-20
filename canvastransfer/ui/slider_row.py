"""Photoshop-style slider control shared by the side panels."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QSlider, QSpinBox, QVBoxLayout, QWidget


def _track_style(colors: list[str]) -> str:
    stops = ", ".join(f"stop:{i / (len(colors) - 1):.2f} {c}" for i, c in enumerate(colors))
    return (
        "QSlider::groove:horizontal { height: 4px; border-radius: 2px;"
        f" background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {stops}); }}"
        "QSlider::handle:horizontal { background: #f2f2f2; border: 1px solid #5a5a5a;"
        " width: 12px; margin: -6px 0; border-radius: 3px; }"
        "QSlider::handle:horizontal:disabled { background: #b0b0b0; }"
    )


class ValueSliderRow:
    """Photoshop-style control: label with an editable number box on top,
    colored track below; slider and box stay in sync. For non-integer
    displays (midtones gamma) pass `decimals` plus the two conversions."""

    def __init__(self, layout: QVBoxLayout, label: str, lo: int, hi: int, value: int, colors: list[str],
                 tooltip: str = "", decimals: int = 0, to_display=None, from_display=None):
        self._to_display = to_display or (lambda v: v)
        self._from_display = from_display or (lambda v: v)

        top = QHBoxLayout()
        self.label = QLabel(f"{label}:")
        if decimals:
            self.spin = QDoubleSpinBox()
            self.spin.setDecimals(decimals)
            self.spin.setSingleStep(10 ** -decimals)
        else:
            self.spin = QSpinBox()
        self.spin.setButtonSymbols(QSpinBox.NoButtons)
        self.spin.setAlignment(Qt.AlignRight)
        self.spin.setFixedWidth(64)
        self.spin.setKeyboardTracking(False)  # apply on Return / leaving the box, not every keystroke
        top.addWidget(self.label)
        top.addStretch(1)
        top.addWidget(self.spin)
        layout.addLayout(top)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setStyleSheet(_track_style(colors))
        layout.addWidget(self.slider)
        if tooltip:
            for w in (self.label, self.slider, self.spin):
                w.setToolTip(tooltip)

        self.set_range(lo, hi)
        self.slider.valueChanged.connect(self._slider_moved)
        self.spin.valueChanged.connect(lambda v: self.slider.setValue(round(self._from_display(v))))
        self.set(value)

    def set_range(self, lo: int, hi: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setRange(lo, hi)
        self.slider.blockSignals(False)
        self.spin.blockSignals(True)
        self.spin.setRange(self._to_display(lo), self._to_display(hi))
        self.spin.blockSignals(False)

    def _slider_moved(self, value: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(self._to_display(value))
        self.spin.blockSignals(False)

    def set(self, value: int) -> None:
        self.slider.setValue(value)
        self._slider_moved(value)

    def widgets(self) -> list[QWidget]:
        return [self.slider, self.spin]
