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
