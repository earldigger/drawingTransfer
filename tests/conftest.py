import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# keep the paint library out of the real app data folder
os.environ["CANVASTRANSFER_DATA_DIR"] = tempfile.mkdtemp(prefix="canvastransfer-test-")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def no_save_prompt(monkeypatch):
    """Closing a window with a never-saved project asks whether to save it;
    tests answer "don't save" unless they set their own answer."""
    from canvastransfer.ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_ask_save_unsaved", lambda self, name: "discard")
