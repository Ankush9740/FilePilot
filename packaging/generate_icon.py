"""Deterministically render the existing SVG into a Windows multi-image ICO.

Qt renders each resolution directly (no resampling). Small images use Windows
32-bit BGRA DIBs plus AND masks; the 256 image uses PNG. No extra imaging library.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "filepilot" / "ui" / "assets" / "filepilot.svg"
TARGET = ROOT / "packaging" / "assets" / "FilePilot.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def encode(image: QImage, size: int) -> bytes:
    if size == 256:
        data = QByteArray()
        buffer = QBuffer(data)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(buffer, "PNG"):
            raise RuntimeError("Could not encode 256px icon")
        return bytes(data)
    # DIB scan lines run bottom-up. Both scan lines and masks are DWORD aligned.
    pixels = bytearray()
    mask = bytearray()
    mask_stride = ((size + 31) // 32) * 4
    for y in reversed(range(size)):
        row_mask = bytearray(mask_stride)
        for x in range(size):
            color = image.pixelColor(x, y)
            pixels.extend((color.blue(), color.green(), color.red(), color.alpha()))
            if color.alpha() == 0:
                row_mask[x // 8] |= 1 << (7 - x % 8)
        mask.extend(row_mask)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         len(pixels) + len(mask), 0, 0, 0, 0)
    return header + pixels + mask


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid source SVG: {SOURCE}")
    payloads = [encode(render(renderer, size), size) for size in SIZES]
    offset = 6 + 16 * len(SIZES)
    entries = []
    for size, payload in zip(SIZES, payloads, strict=True):
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                                   1, 32, len(payload), offset))
        offset += len(payload)
    content = struct.pack("<HHH", 0, 1, len(SIZES)) + b"".join(entries + payloads)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    # Avoid changing the checked-in icon's timestamp on identical builds.
    if not TARGET.exists() or TARGET.read_bytes() != content:
        TARGET.write_bytes(content)
    print(f"Icon: {TARGET} ({', '.join(map(str, SIZES))} px)")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
