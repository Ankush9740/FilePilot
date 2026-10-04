"""Exercise the actual desktop entry point with a temporary database and timed exit."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from filepilot.main import main
from filepilot.ui.window import MainWindow


def smoke() -> int:
    original_show = MainWindow.show
    result = {}
    def show_and_check(window):
        original_show(window)
        timer = QTimer(window)
        timeout = QTimer(window)
        timeout.setSingleShot(True)
        timeout.timeout.connect(lambda: QApplication.instance().exit(2))
        timeout.start(15_000)
        def check():
            if window.job is None and window.state.scan is not None:
                result.update(platform=QApplication.platformName(), files=len(window.state.scan.files),
                              database=window.store.path.exists(), empty_history=not window.store.history())
                if result["files"] != 2 or not result["database"]:
                    QApplication.instance().exit(3)
                    return
                timer.stop()
                timeout.stop()
                def capture():
                    output = Path(__file__).parent / "output"
                    output.mkdir(exist_ok=True)
                    window.grab().save(str(output / "native-startup.png"))
                    window.close()
                QTimer.singleShot(150, capture)
        timer.timeout.connect(check)
        timer.start(50)
    MainWindow.show = show_and_check
    with tempfile.TemporaryDirectory(prefix="filepilot-native-") as temporary:
        base = Path(temporary)
        folder = base / "scan-fixture"
        folder.mkdir()
        (folder / "read-only.txt").write_text("read-only startup fixture")
        (folder / "picture.png").write_bytes(b"metadata fixture, not an image")
        sys.argv = ["FilePilot", "--data-dir", str(base / "data"), "--folder", str(folder)]
        code = main()
        assert (folder / "read-only.txt").read_text() == "read-only startup fixture"
        assert not (folder / "Documents").exists()
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(smoke())
