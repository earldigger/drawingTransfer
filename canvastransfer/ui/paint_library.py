"""The Paint Library window: your paints grouped by medium, with import from
a saved artistpigments.org collection page, add / edit / delete, favorites,
and which paints are offered in matches."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .. import color_study as cs
from ..paints import OPACITY_LABELS, SOURCE_LABELS, Paint, PaintLibrary, medium_label, parse_collection_html
from .paint_dialog import OFF_SCREEN_NOTE, PaintDialog

PAINT_ID_ROLE = Qt.UserRole + 1
COL_FAVORITE, COL_USE, COL_NAME, COL_BRAND, COL_CODE, COL_PIGMENTS, COL_OPACITY, COL_DATA = range(8)
HEADERS = ["★", "Use", "Paint", "Brand", "Code", "Pigments", "Opacity", "Color data"]


def library_path() -> Path:
    """paints.json in the app's data folder (on a Mac:
    ~/Library/Application Support/Canvas Transfer). CANVASTRANSFER_DATA_DIR
    overrides it, which the tests use."""
    import os

    override = os.environ.get("CANVASTRANSFER_DATA_DIR")
    base = Path(override) if override else Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    return base / "paints.json"


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


def color_data_text(library: PaintLibrary, paint: Paint) -> tuple[str, str, bool]:
    """(short text, tooltip, off screen) for the Color data column."""
    if paint.lab is not None:
        _, in_gamut = cs.lab_d50_to_srgb(paint.lab)
        text = paint.source or "Measured"
        tip = SOURCE_LABELS.get(paint.source, paint.source) + "\nL* {:.2f}  a* {:.2f}  b* {:.2f} (D50)".format(*paint.lab)
        return (("⚠ " if not in_gamut else "") + text, tip + ("" if in_gamut else "\n" + OFF_SCREEN_NOTE), not in_gamut)
    stand_in = library.stand_in_for(paint)
    if stand_in is None:
        return "No color data", "Not used in matching. Edit the paint to paste its color or choose a stand-in.", False
    how = "chosen" if paint.stand_in else "automatic"
    _, in_gamut = cs.lab_d50_to_srgb(stand_in.lab)
    return ((("⚠ " if not in_gamut else "") + f"Stand-in: {stand_in.name}"),
            f"No color data of its own; uses {stand_in.label()} ({how})."
            + ("" if in_gamut else "\n" + OFF_SCREEN_NOTE), not in_gamut)


class PaintLibraryDialog(QDialog):
    libraryChanged = Signal()

    def __init__(self, library: PaintLibrary, parent=None):
        super().__init__(parent)
        self.library = library
        self._updating = False
        self.setWindowTitle("Paint Library")
        self.resize(1100, 680)

        buttons = QHBoxLayout()
        self.import_button = QPushButton("Import Saved Page…")
        self.import_button.setToolTip("Import paints from an artistpigments.org collection page saved with "
                                      "File > Save Page As. Importing again updates paints and keeps your choices.")
        self.import_button.clicked.connect(self.import_page)
        self.add_button = QPushButton("Add Paint…")
        self.add_button.clicked.connect(self.add_paint)
        self.edit_button = QPushButton("Edit…")
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_selected)
        self.web_button = QPushButton("Open Web Page")
        self.web_button.clicked.connect(self.open_web_page)
        for b in (self.import_button, self.add_button, self.edit_button, self.delete_button, self.web_button):
            buttons.addWidget(b)
        buttons.addStretch(1)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(HEADERS)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemDoubleClicked.connect(lambda item, _col: self.edit_selected())
        self.tree.currentItemChanged.connect(lambda *_: self._update_buttons())

        self.summary = QLabel()
        self.summary.setStyleSheet("color: gray;")
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(close)

        v = QVBoxLayout(self)
        v.addLayout(buttons)
        v.addWidget(self.tree, 1)
        v.addLayout(bottom)
        self.refresh()

    # -- display ---------------------------------------------------------------

    def refresh(self, select_id: str | None = None) -> None:
        select_id = select_id or self.selected_id()
        self._updating = True
        self.tree.clear()
        bold = QFont()
        bold.setBold(True)
        measured = stand_ins = missing = 0
        for medium in self.library.media():
            paints = sorted(self.library.in_medium(medium),
                            key=lambda p: (not p.favorite, p.brand.lower(), p.name.lower()))
            group = QTreeWidgetItem([""] * len(HEADERS))
            group.setText(COL_NAME, f"{medium_label(medium)}  ({len(paints)})")
            group.setFont(COL_NAME, bold)
            group.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(group)
            for p in paints:
                item = QTreeWidgetItem([""] * len(HEADERS))
                item.setData(0, PAINT_ID_ROLE, p.id)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                item.setCheckState(COL_FAVORITE, Qt.Checked if p.favorite else Qt.Unchecked)
                item.setToolTip(COL_FAVORITE, "Favorite (listed first; can limit matches to favorites)")
                item.setCheckState(COL_USE, Qt.Checked if p.enabled else Qt.Unchecked)
                item.setToolTip(COL_USE, "Offer this paint in matches and mixes")
                lab = self.library.color_of(p)
                rgb = cs.lab_d50_to_srgb(lab)[0] if lab else None
                item.setIcon(COL_NAME, paint_chip(rgb, dashed=p.lab is None))
                item.setText(COL_NAME, p.name)
                item.setText(COL_BRAND, p.brand)
                item.setText(COL_CODE, p.code)
                item.setText(COL_PIGMENTS, ", ".join(p.pigments))
                item.setText(COL_OPACITY, OPACITY_LABELS.get(p.opacity, p.opacity))
                text, tip, off = color_data_text(self.library, p)
                item.setText(COL_DATA, text)
                item.setToolTip(COL_DATA, tip)
                if off:
                    item.setForeground(COL_DATA, QColor(180, 110, 0))
                if p.lab is None and lab is None:
                    item.setForeground(COL_DATA, QColor(170, 60, 60))
                group.addChild(item)
                if p.id == select_id:
                    self.tree.setCurrentItem(item)
                if p.lab is not None:
                    measured += 1
                elif lab is not None:
                    stand_ins += 1
                else:
                    missing += 1
            group.setExpanded(True)
        total = len(self.library.paints)
        self.summary.setText(f"{total} paints · {measured} measured · {stand_ins} using a stand-in · "
                             f"{missing} without color data · ⚠ = can't be shown exactly on screen" if total else
                             "No paints yet. Save your artistpigments.org collection page in your browser "
                             "(File > Save Page As), then click Import Saved Page.")
        self._updating = False
        self._update_buttons()

    def selected_id(self) -> str | None:
        item = self.tree.currentItem()
        return item.data(0, PAINT_ID_ROLE) if item else None

    def _update_buttons(self) -> None:
        paint = self.library.get(self.selected_id())
        for b in (self.edit_button, self.delete_button):
            b.setEnabled(paint is not None)
        self.web_button.setEnabled(bool(paint and paint.url))

    def _changed(self, select_id: str | None = None) -> None:
        self.library.changed()
        self.refresh(select_id)
        self.libraryChanged.emit()

    # -- actions ---------------------------------------------------------------

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating:
            return
        paint = self.library.get(item.data(0, PAINT_ID_ROLE))
        if paint is None:
            return
        if column == COL_FAVORITE:
            paint.favorite = item.checkState(COL_FAVORITE) == Qt.Checked
        elif column == COL_USE:
            paint.enabled = item.checkState(COL_USE) == Qt.Checked
        else:
            return
        self._changed(paint.id)

    def import_page(self, path: str | None = None) -> None:
        if not path:
            start = str(Path.home() / "Downloads")
            path, _ = QFileDialog.getOpenFileName(self, "Import Saved Collection Page", start,
                                                  "Saved web pages (*.html *.htm)")
        if not path:
            return
        try:
            title, paints = parse_collection_html(Path(path).read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Import", str(e))
            return
        added, updated = self.library.merge(paints)
        self.refresh()
        self.libraryChanged.emit()
        no_data = [self.library.get(p.id) for p in paints if p.lab is None]
        without = [p for p in no_data if self.library.color_of(p) is None]
        kept = len(self.library.paints) - added - updated
        QMessageBox.information(
            self, "Import",
            f"“{title}”: {added} paints added, {updated} updated.\n\n"
            f"{len(no_data) - len(without)} paints without color data use a stand-in; "
            f"{len(without)} have none yet and are left out of matching."
            + (f"\n\n{kept} paints already in the library but not on this page were kept." if kept else ""))

    def add_paint(self) -> None:
        current = self.library.get(self.selected_id())
        dialog = PaintDialog(self.library, medium=current.medium if current else "oil", parent=self)
        if dialog.exec() == QDialog.Accepted:
            paint = dialog.result_paint()
            self.library.paints.append(paint)
            self._changed(paint.id)

    def edit_selected(self) -> None:
        paint = self.library.get(self.selected_id())
        if paint is None:
            return
        dialog = PaintDialog(self.library, paint, parent=self)
        if dialog.exec() == QDialog.Accepted:
            dialog.result_paint()
            self._changed(paint.id)

    def delete_selected(self) -> None:
        paint = self.library.get(self.selected_id())
        if paint is None:
            return
        if QMessageBox.question(self, "Delete Paint", f"Delete {paint.label()} from the library?") != QMessageBox.Yes:
            return
        self.library.remove(paint.id)
        self.refresh()
        self.libraryChanged.emit()

    def open_web_page(self) -> None:
        paint = self.library.get(self.selected_id())
        if paint and paint.url:
            QDesktopServices.openUrl(QUrl(paint.url))
