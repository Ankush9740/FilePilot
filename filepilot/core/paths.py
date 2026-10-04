import os
from pathlib import Path


def data_directory() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "FilePilot"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "FilePilot"


def application_directory() -> Path:
    return Path(__file__).resolve().parents[2]
