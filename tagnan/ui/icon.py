"""Write Tagnan's icon (the Mousquetaire, 256 px) as an .ico file: python -m tagnan.ui.icon PATH"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter

from tagnan import art
from tagnan.ui.images import render_svg

GRADE = 3  # the Mousquetaire: casaque, cross and plume


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage : python -m tagnan.ui.icon CHEMIN.ico", file=sys.stderr)
        return 2
    app = QGuiApplication(sys.argv[:1])
    figure = render_svg(art.still_svg(GRADE, glow=False), round(256 * 120 / 140), 256)
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.drawImage((256 - figure.width()) // 2, 0, figure)
    painter.end()
    # The format comes from the .ico suffix: PySide6 refuses it as bytes, the stubs as str.
    ok = image.save(sys.argv[1])
    del app
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
