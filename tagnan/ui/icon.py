"""Write Tagnan's icon (the inkwell drawn for small sizes, 256 px), as .ico for Windows or .png
for macOS (the format follows the suffix): python -m tagnan.ui.icon PATH"""

import sys

from PySide6.QtGui import QGuiApplication, QImage

from tagnan import art
from tagnan.ui.images import render_svg


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m tagnan.ui.icon PATH.ico|PATH.png", file=sys.stderr)
        return 2
    app = QGuiApplication(sys.argv[:1])
    image = render_svg(art.icon_svg(), 256, 256).convertToFormat(QImage.Format.Format_ARGB32)
    # The format comes from the .ico suffix: PySide6 refuses it as bytes, the stubs as str.
    ok = image.save(sys.argv[1])
    del app
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
