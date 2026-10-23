"""The start screen, shown when no project is open: New Project, Open
Project, and recent projects as thumbnail cards (click one to open it)."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .projects_folder import projects_folder
from .recent_projects import Recent, recent_projects, remove_recent

CARD = QSize(220, 160)
PATH_ROLE = Qt.UserRole + 1


def card_icon(recent: Recent) -> QIcon:
    """The project's saved thumbnail fitted on a card, or a plain card with
    the project's initial when it has none yet."""
    pm = QPixmap(CARD)
    pm.fill(QColor(58, 58, 58))
    p = QPainter(pm)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setRenderHint(QPainter.Antialiasing)
    image = QImage(str(recent.thumbnail)) if recent.thumbnail.is_file() else QImage()
    if not image.isNull():
        scaled = image.scaled(CARD - QSize(12, 12), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x, y = (CARD.width() - scaled.width()) / 2, (CARD.height() - scaled.height()) / 2
        p.drawImage(int(x), int(y), scaled)
        p.setPen(QPen(QColor(20, 20, 20), 1))
        p.drawRect(QRectF(x - 0.5, y - 0.5, scaled.width(), scaled.height()))
    else:
        p.setBrush(QColor(245, 242, 235))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(50, 22, CARD.width() - 100, CARD.height() - 44))
        f = QFont()
        f.setPixelSize(40)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(150, 150, 150))
        p.drawText(QRectF(0, 0, CARD.width(), CARD.height()), Qt.AlignCenter, (recent.name[:1] or "?").upper())
    p.end()
    return QIcon(pm)


def when(timestamp: float) -> str:
    t = time.localtime(timestamp)
    now = time.localtime()
    if t.tm_year == now.tm_year and t.tm_yday == now.tm_yday:
        return "Today " + time.strftime("%H:%M", t)
    if t.tm_year == now.tm_year and t.tm_yday == now.tm_yday - 1:
        return "Yesterday " + time.strftime("%H:%M", t)
    return time.strftime("%b %d" if t.tm_year == now.tm_year else "%b %d, %Y", t).replace(" 0", " ")


class StartScreen(QWidget):
    newRequested = Signal()
    openRequested = Signal()
    recentChosen = Signal(str)
    folderChangeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("startScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)  # so the dark background is painted
        self.setStyleSheet("#startScreen { background: #2b2b2b; } "
                           "#startScreen QLabel { color: #e8e8e8; } "
                           "#startScreen QLabel#hint { color: #9a9a9a; }")

        title = QLabel("Canvas Transfer")
        f = title.font()
        f.setPointSize(f.pointSize() + 14)
        f.setBold(True)
        title.setFont(f)
        subtitle = QLabel("Transfer a drawing onto your canvas")
        subtitle.setObjectName("hint")

        self.new_button = QPushButton("New Project…")
        self.open_button = QPushButton("Open Project…")
        for b, tip in ((self.new_button, "Start a project for a canvas size (Cmd+N)"),
                       (self.open_button, "Open a saved .ctproj project (Cmd+O)")):
            b.setMinimumSize(QSize(200, 44))
            b.setToolTip(tip)
        self.new_button.clicked.connect(self.newRequested.emit)
        self.open_button.clicked.connect(self.openRequested.emit)

        left = QVBoxLayout()
        left.addWidget(title)
        left.addWidget(subtitle)
        left.addSpacing(30)
        left.addWidget(self.new_button)
        left.addWidget(self.open_button)
        left.addStretch(1)
        self.folder_label = QLabel()
        self.folder_label.setObjectName("hint")
        self.folder_label.setWordWrap(True)
        self.folder_label.setMaximumWidth(300)
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.folder_button = QPushButton("Change Folder…")
        self.folder_button.setToolTip("Where new projects are saved (they autosave from the start)")
        self.folder_button.clicked.connect(self.folderChangeRequested.emit)
        left.addWidget(self.folder_label)
        left.addWidget(self.folder_button, alignment=Qt.AlignLeft)

        recent_title = QLabel("Recent Projects")
        f = recent_title.font()
        f.setPointSize(f.pointSize() + 4)
        f.setBold(True)
        recent_title.setFont(f)
        self.recent_list = QListWidget()
        self.recent_list.setViewMode(QListView.IconMode)
        self.recent_list.setIconSize(CARD)
        self.recent_list.setGridSize(QSize(CARD.width() + 24, CARD.height() + 56))
        self.recent_list.setResizeMode(QListView.Adjust)
        self.recent_list.setMovement(QListView.Static)
        self.recent_list.setWordWrap(True)
        self.recent_list.setSpacing(4)
        self.recent_list.setStyleSheet("QListWidget { background: #2b2b2b; border: none; color: #e8e8e8; }")
        self.recent_list.itemClicked.connect(lambda item: self.recentChosen.emit(item.data(PATH_ROLE)))
        self.recent_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recent_list.customContextMenuRequested.connect(self._context_menu)
        self.empty_label = QLabel("No recent projects yet. New projects show up here right away.")
        self.empty_label.setObjectName("hint")

        right = QVBoxLayout()
        right.addWidget(recent_title)
        right.addWidget(self.empty_label)
        right.addWidget(self.recent_list, 1)
        right.addStretch(0)  # keeps the title and hint at the top when there are no recents

        layout = QHBoxLayout(self)
        layout.setContentsMargins(48, 40, 32, 24)
        layout.addLayout(left)
        layout.addSpacing(40)
        layout.addLayout(right, 1)
        self.refresh()

    def refresh(self) -> None:
        self.folder_label.setText(f"New projects are saved in:\n{projects_folder()}")
        self.recent_list.clear()
        recents = recent_projects()
        for r in recents:
            item = QListWidgetItem(card_icon(r), f"{r.name}\n{when(r.opened)}")
            item.setData(PATH_ROLE, str(r.path))
            item.setToolTip(str(r.path))
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.recent_list.addItem(item)
        self.empty_label.setVisible(not recents)
        self.recent_list.setVisible(bool(recents))

    def _context_menu(self, pos) -> None:
        item = self.recent_list.itemAt(pos)
        if item is None:
            return
        path = item.data(PATH_ROLE)
        menu = QMenu(self)
        menu.addAction("Open", lambda: self.recentChosen.emit(path))
        menu.addAction("Show in Finder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent))))
        menu.addSeparator()
        menu.addAction("Remove from Recents", lambda: (remove_recent(path), self.refresh()))
        menu.exec(self.recent_list.viewport().mapToGlobal(pos))
