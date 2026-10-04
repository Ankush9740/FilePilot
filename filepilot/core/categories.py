from enum import StrEnum
from pathlib import Path


class Category(StrEnum):
    DOCUMENTS = "Documents"
    IMAGES = "Images"
    VIDEOS = "Videos"
    AUDIO = "Audio"
    ARCHIVES = "Archives"
    INSTALLERS = "Installers"
    CODE = "Code"
    OTHER = "Other"


EXTENSIONS: dict[Category, frozenset[str]] = {
    Category.DOCUMENTS: frozenset("pdf doc docx xls xlsx ppt pptx txt rtf odt ods odp csv tsv epub md".split()),
    Category.IMAGES: frozenset("jpg jpeg png gif webp bmp svg tif tiff heic avif ico raw".split()),
    Category.VIDEOS: frozenset("mp4 mkv mov avi webm m4v wmv mpg mpeg".split()),
    Category.AUDIO: frozenset("mp3 wav flac aac ogg m4a wma aiff opus".split()),
    Category.ARCHIVES: frozenset("zip rar 7z tar gz bz2 xz tgz zst".split()),
    Category.INSTALLERS: frozenset("exe msi msix appx iso dmg pkg".split()),
    Category.CODE: frozenset("py pyw js ts jsx tsx html css scss json yaml yml toml xml sql c cpp h hpp cs java go rs rb php sh ps1 bat ipynb".split()),
    Category.OTHER: frozenset(),
}
EXTENSION_CATEGORY = {f".{ext}": category for category, exts in EXTENSIONS.items() for ext in exts}
CATEGORY_COLORS = {
    Category.DOCUMENTS: "#477B6B", Category.IMAGES: "#B48751",
    Category.VIDEOS: "#6B7E9A", Category.AUDIO: "#9B7075",
    Category.ARCHIVES: "#91815A", Category.INSTALLERS: "#718486",
    Category.CODE: "#778259", Category.OTHER: "#99958D",
}


def classify(path: Path | str) -> Category:
    return EXTENSION_CATEGORY.get(Path(path).suffix.lower(), Category.OTHER)


def human_size(size: int) -> str:
    value = float(max(0, size))
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("Unreachable")
