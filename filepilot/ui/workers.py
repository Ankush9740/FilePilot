import traceback
from collections.abc import Callable
from threading import Event
from typing import Any

from PySide6.QtCore import QThread, Signal

from filepilot.core.safety import Cancelled


class Job(QThread):
    progress = Signal(int, int, str)

    def __init__(self, function: Callable[[Event, Callable], Any]) -> None:
        super().__init__()
        self.function = function
        self.cancel_event = Event()
        self.result: Any = None
        self.error: str | None = None
        self.cancelled = False

    def run(self) -> None:
        try:
            self.result = self.function(self.cancel_event, self.progress.emit)
        except Cancelled:
            self.cancelled = True
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}\n\n{traceback.format_exc()}"

    def cancel(self) -> None:
        self.cancel_event.set()
