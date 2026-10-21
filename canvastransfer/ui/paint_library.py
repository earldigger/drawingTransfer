"""The Paint Library window: your paints grouped by medium, with import from
a saved artistpigments.org collection page, add / edit / delete, favorites,
and which paints are offered in matches; plus your limited palettes and the
classic ones, filled from the paints you own."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import color_study as cs
from .. import palettes
from ..paints import (
    OPACITY_LABELS,
    SOURCE_LABELS,
    Paint,
    PaintLibrary,
    Palette,
    field_label,
    medium_label,
    new_palette_id,
    parse_collection_html,
)
from .library_location import choose_folder, move_library
from .paint_dialog import OFF_SCREEN_NOTE, PaintDialog, paint_chip
from .palette_dialog import PaletteDialog

PAINT_ID_ROLE = Qt.UserRole + 1
SOURCE_ROLE = Qt.UserRole + 2  # ("palette", id) or ("template", key)
(COL_FAVORITE, COL_USE, COL_NAME, COL_BRAND, COL_CODE, COL_SERIES, COL_PIGMENTS, COL_OPACITY, COL_DRYING,
 COL_DATA) = range(10)
HEADERS = ["★", "Use", "Paint", "Brand", "Code", "Series", "Pigments", "Opacity", "Drying", "Color data"]
HEADER_TIPS = {COL_CODE: "The maker's catalog number for the color",
               COL_SERIES: "The maker's price series (from artistpigments.org, or entered by you)",
               COL_DRYING: "Drying time, entered by you"}
EDITED_MARK = " ✎"


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
        self.revert_button = QPushButton("Revert to Site Data")
        self.revert_button.setToolTip("Undo your edits to this paint's site fields (name, pigments, color, ...) and "
                                      "use the values from the last import. Drying time and your choices stay.")
        self.revert_button.clicked.connect(self.revert_selected)
        self.web_button = QPushButton("Open Web Page")
        self.web_button.clicked.connect(self.open_web_page)
        for b in (self.import_button, self.add_button, self.edit_button, self.delete_button, self.revert_button,
                  self.web_button):
            buttons.addWidget(b)
        buttons.addStretch(1)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(HEADERS)
        for col, tip in HEADER_TIPS.items():
            self.tree.headerItem().setToolTip(col, tip)
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
        self.location_label = QLabel()
        self.location_label.setStyleSheet("color: gray;")
        self.location_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.location_button = QPushButton("Change Location…")
        self.location_button.setToolTip("Keep the library file in another folder, such as Dropbox")
        self.location_button.clicked.connect(self.change_location)
        location = QHBoxLayout()
        location.addWidget(self.location_label, 1)
        location.addWidget(self.location_button)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(close)

        paints_page = QWidget()
        pv = QVBoxLayout(paints_page)
        pv.addLayout(buttons)
        pv.addWidget(self.tree, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(paints_page, "Paints")
        self.tabs.addTab(self._build_palettes_page(), "Palettes")

        v = QVBoxLayout(self)
        v.addWidget(self.tabs, 1)
        v.addLayout(location)
        v.addLayout(bottom)
        self.refresh()
        self.refresh_palettes()

    def _build_palettes_page(self) -> QWidget:
        page = QWidget()
        buttons = QHBoxLayout()
        self.new_palette_button = QPushButton("New Palette…")
        self.new_palette_button.clicked.connect(self.new_palette)
        self.edit_palette_button = QPushButton("Edit…")
        self.edit_palette_button.clicked.connect(self.edit_palette)
        self.duplicate_palette_button = QPushButton("Duplicate as My Palette")
        self.duplicate_palette_button.setToolTip("Copy this palette into one of yours, which you can change")
        self.duplicate_palette_button.clicked.connect(self.duplicate_palette)
        self.delete_palette_button = QPushButton("Delete")
        self.delete_palette_button.clicked.connect(self.delete_palette)
        for b in (self.new_palette_button, self.edit_palette_button, self.duplicate_palette_button,
                  self.delete_palette_button):
            buttons.addWidget(b)
        buttons.addStretch(1)

        self.palette_list = QListWidget()
        self.palette_list.currentItemChanged.connect(lambda *_: self._show_palette())
        self.palette_list.itemDoubleClicked.connect(lambda *_: self.edit_palette())

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.palette_medium_label = QLabel("Fill from")
        self.palette_medium = QComboBox()
        self.palette_medium.setToolTip("Which of your paint groups a classic palette is filled from")
        self.palette_medium.currentIndexChanged.connect(lambda *_: self._show_palette())
        row.addWidget(self.palette_medium_label)
        row.addWidget(self.palette_medium)
        row.addStretch(1)
        rv.addLayout(row)
        self.palette_note = QLabel()
        self.palette_note.setWordWrap(True)
        rv.addWidget(self.palette_note)
        self.palette_contents = QListWidget()
        self.palette_contents.setSelectionMode(QListWidget.NoSelection)
        rv.addWidget(self.palette_contents, 1)

        split = QSplitter()
        split.addWidget(self.palette_list)
        split.addWidget(right)
        split.setSizes([300, 700])
        v = QVBoxLayout(page)
        v.addLayout(buttons)
        v.addWidget(split, 1)
        return page

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
                item.setText(COL_NAME, p.name + (EDITED_MARK if p.edited else ""))
                item.setToolTip(COL_NAME, f"{p.label()}" + (
                    f"\nEdited in the app: {', '.join(field_label(f) for f in p.edited)}. "
                    "Importing again keeps your values." if p.edited else
                    ("\nAdded by hand" if p.manual else "")))
                item.setText(COL_BRAND, p.brand)
                item.setText(COL_CODE, p.code)
                item.setText(COL_SERIES, p.series)
                item.setText(COL_PIGMENTS, ", ".join(p.pigments))
                item.setText(COL_OPACITY, OPACITY_LABELS.get(p.opacity, p.opacity))
                item.setText(COL_DRYING, p.drying)
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
        self.location_label.setText(f"Saved in: {self.library.path}" if self.library.path else "Not saved")
        self._updating = False
        self._update_buttons()

    # -- palettes ------------------------------------------------------------

    def open_palettes_tab(self) -> None:
        self.tabs.setCurrentIndex(1)

    def refresh_palettes(self, select: tuple | None = None) -> None:
        select = select or self.selected_source()
        self.palette_list.blockSignals(True)
        self.palette_list.clear()
        bold = QFont()
        bold.setBold(True)

        def header(text):
            item = QListWidgetItem(text)
            item.setFont(bold)
            item.setFlags(Qt.ItemIsEnabled)
            self.palette_list.addItem(item)

        header("My palettes")
        if not self.library.palettes:
            note = QListWidgetItem("   (none yet: New Palette, or duplicate a classic one)")
            note.setFlags(Qt.ItemIsEnabled)
            note.setForeground(QColor(130, 130, 130))
            self.palette_list.addItem(note)
        for p in self.library.palettes:
            item = QListWidgetItem(f"{p.name}   ({medium_label(p.medium)}, {len(p.paint_ids)})")
            item.setData(SOURCE_ROLE, ("palette", p.id))
            self.palette_list.addItem(item)
        header("Classic palettes")
        for t in palettes.TEMPLATES:
            item = QListWidgetItem(t.name)
            item.setData(SOURCE_ROLE, ("template", t.key))
            item.setToolTip(t.note)
            self.palette_list.addItem(item)
        current = None
        for i in range(self.palette_list.count()):
            if self.palette_list.item(i).data(SOURCE_ROLE) == select:
                current = self.palette_list.item(i)
        self.palette_list.blockSignals(False)
        keep = self.palette_medium.currentData()
        self.palette_medium.blockSignals(True)
        self.palette_medium.clear()
        for m in self.library.media() or ["oil"]:
            self.palette_medium.addItem(medium_label(m), m)
        self.palette_medium.setCurrentIndex(max(0, self.palette_medium.findData(keep)))
        self.palette_medium.blockSignals(False)
        if current is not None:
            self.palette_list.setCurrentItem(current)
        self._show_palette()

    def selected_source(self) -> tuple | None:
        item = self.palette_list.currentItem() if hasattr(self, "palette_list") else None
        data = item.data(SOURCE_ROLE) if item else None
        return tuple(data) if data else None

    def select_source(self, source: tuple) -> None:
        for i in range(self.palette_list.count()):
            if self.palette_list.item(i).data(SOURCE_ROLE) == source:
                self.palette_list.setCurrentRow(i)

    def _add_content_row(self, paint: Paint | None, text: str, tip: str = "", warn: bool = False) -> None:
        lab = self.library.color_of(paint) if paint else None
        rgb = cs.lab_d50_to_srgb(lab)[0] if lab else None
        item = QListWidgetItem(paint_chip(rgb, size=22, dashed=bool(paint) and paint.lab is None), text)
        item.setToolTip(tip)
        if warn:
            item.setForeground(QColor(170, 60, 60))
        self.palette_contents.addItem(item)

    def _show_palette(self) -> None:
        self.palette_contents.clear()
        source = self.selected_source()
        kind = source[0] if source else None
        self.palette_medium.setVisible(kind == "template")
        self.palette_medium_label.setVisible(kind == "template")
        self.edit_palette_button.setEnabled(kind == "palette")
        self.delete_palette_button.setEnabled(kind == "palette")
        self.duplicate_palette_button.setEnabled(kind is not None)
        if kind == "palette":
            palette = self.library.get_palette(source[1])
            self.palette_note.setText(f"<b>{palette.name}</b> — {medium_label(palette.medium)}")
            for paint in self.library.palette_paints(palette):
                has_color = self.library.color_of(paint) is not None
                self._add_content_row(paint, f"{paint.name} — {paint.brand}"
                                      + ("" if has_color else "   (no color data: left out of mixing)"),
                                      paint.label(), warn=not has_color)
        elif kind == "template":
            filled = palettes.fill(palettes.template(source[1]), self.library, self.palette_medium.currentData())
            self.palette_note.setText(f"<b>{filled.template.name}</b><br>{filled.template.note}")
            for f in filled.roles:
                if f.paint is None:
                    self._add_content_row(None, f"{f.role.name}:  none of your paints fits", warn=True)
                else:
                    self._add_content_row(f.paint, f"{f.role.name}:  {f.paint.name} — {f.paint.brand}"
                                          + ("   (substitute)" if f.substitute else ""), f.paint.label())
        else:
            self.palette_note.setText("Select a palette.")

    def _palette_changed(self, select: tuple | None) -> None:
        self.library.changed()
        self.refresh_palettes(select)
        self.libraryChanged.emit()

    def new_palette(self) -> None:
        dialog = PaletteDialog(self.library, medium=self.palette_medium.currentData() or "oil", parent=self)
        if dialog.exec() == QDialog.Accepted:
            palette = dialog.result_palette()
            self.library.palettes.append(palette)
            self._palette_changed(("palette", palette.id))

    def edit_palette(self) -> None:
        source = self.selected_source()
        palette = self.library.get_palette(source[1]) if source and source[0] == "palette" else None
        if palette is None:
            return
        dialog = PaletteDialog(self.library, palette, parent=self)
        if dialog.exec() == QDialog.Accepted:
            dialog.result_palette()
            self._palette_changed(("palette", palette.id))

    def duplicate_palette(self) -> None:
        source = self.selected_source()
        if source is None:
            return
        if source[0] == "palette":
            original = self.library.get_palette(source[1])
            copy = Palette(new_palette_id(), f"{original.name} copy", original.medium, list(original.paint_ids))
        else:
            filled = palettes.fill(palettes.template(source[1]), self.library, self.palette_medium.currentData())
            copy = Palette(new_palette_id(), f"My {filled.template.name}", filled.medium,
                           [p.id for p in filled.paints()])
        self.library.palettes.append(copy)
        self._palette_changed(("palette", copy.id))

    def delete_palette(self) -> None:
        source = self.selected_source()
        palette = self.library.get_palette(source[1]) if source and source[0] == "palette" else None
        if palette is None:
            return
        if QMessageBox.question(self, "Delete Palette", f"Delete the palette “{palette.name}”? "
                                "The paints stay in your library.") != QMessageBox.Yes:
            return
        self.library.palettes.remove(palette)
        self._palette_changed(None)

    # -- paints ------------------------------------------------------------------

    def selected_id(self) -> str | None:
        item = self.tree.currentItem()
        return item.data(0, PAINT_ID_ROLE) if item else None

    def _update_buttons(self) -> None:
        paint = self.library.get(self.selected_id())
        for b in (self.edit_button, self.delete_button):
            b.setEnabled(paint is not None)
        self.web_button.setEnabled(bool(paint and paint.url))
        self.revert_button.setEnabled(bool(paint and paint.edited and paint.site))

    def _changed(self, select_id: str | None = None) -> None:
        self.library.changed()
        self.refresh(select_id)
        self.refresh_palettes()
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
        self.library.changed()
        # rebuild the tree after Qt has finished with this item's click: rebuilding
        # now would delete the item while its signal is still running (a crash)
        QTimer.singleShot(0, lambda pid=paint.id: self._after_check(pid))

    def _after_check(self, paint_id: str) -> None:
        self.refresh(paint_id)
        self.refresh_palettes()
        self.libraryChanged.emit()

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
        report = self.library.merge(paints)
        self.refresh()
        self.refresh_palettes()
        self.libraryChanged.emit()
        mine = [self.library.get(p.id) for p in paints]
        no_data = [p for p in mine if p.lab is None]
        without = [p for p in no_data if self.library.color_of(p) is None]
        others = len(self.library.paints) - report.added - report.updated
        edited = [p for p in mine if p.edited]
        text = (f"“{title}”: {report.added} paints added, {report.updated} updated.\n\n"
                f"{len(no_data) - len(without)} paints without color data use a stand-in; "
                f"{len(without)} have none yet and are left out of matching.")
        if edited:
            text += f"\n\nYour edits were kept on {len(edited)} paints."
        if report.kept:
            lines = [f"  • {p.name}: {', '.join(field_label(f) for f in fields)}" for p, fields in report.kept[:12]]
            more = f"\n  … and {len(report.kept) - 12} more" if len(report.kept) > 12 else ""
            text += ("\nThe site has different values where you edited (yours kept; "
                     "use Revert to Site Data to take the site's):\n" + "\n".join(lines) + more)
        if others:
            text += f"\n\n{others} paints in the library but not on this page were kept."
        QMessageBox.information(self, "Import", text)

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

    def revert_selected(self) -> None:
        paint = self.library.get(self.selected_id())
        if paint is None or not paint.edited:
            return
        fields = ", ".join(field_label(f) for f in paint.edited)
        if QMessageBox.question(self, "Revert to Site Data",
                                f"Replace your {fields} for {paint.name} with the values from the last "
                                "import?") != QMessageBox.Yes:
            return
        paint.revert_to_site()
        self._changed(paint.id)

    def change_location(self) -> None:
        folder = choose_folder(self)
        if folder is not None and move_library(self.library, folder, self):
            self.refresh()
            self.refresh_palettes()
            self.libraryChanged.emit()

    def delete_selected(self) -> None:
        paint = self.library.get(self.selected_id())
        if paint is None:
            return
        if QMessageBox.question(self, "Delete Paint", f"Delete {paint.label()} from the library?") != QMessageBox.Yes:
            return
        self.library.remove(paint.id)
        self.refresh()
        self.refresh_palettes()
        self.libraryChanged.emit()

    def open_web_page(self) -> None:
        paint = self.library.get(self.selected_id())
        if paint and paint.url:
            QDesktopServices.openUrl(QUrl(paint.url))
