"""Development: the QML figure alone, offscreen, saved as a strip of frames.

    QT_QPA_PLATFORM=offscreen uv run python -m tagnan.ui.preview build/frames.png \\
        [--grades 0 1 2 3 4 5] [--mood ask] [--tap] [--at 0.4 1.2]

Each row is a grade; each column a moment (seconds after the mood was set or the tap).
"""

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow

from tagnan import art
from tagnan.ui.animation.rig import Rig
from tagnan.ui.animator import Animator
from tagnan.ui.images import LayerImages

QML_DIR = Path(__file__).resolve().parent / "qml"
FIGURE_W, FIGURE_H = 180, 210


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview of the QML figure")
    parser.add_argument("out", type=Path)
    parser.add_argument("--grades", type=int, nargs="+", default=list(range(6)))
    parser.add_argument("--mood", default="idle", choices=["idle", "ask", "happy", "angry"])
    parser.add_argument("--tap", type=int, default=0, help="nombre de tapes")
    parser.add_argument("--at", type=float, nargs="+", default=[1.0])
    parser.add_argument("--light", action="store_true")
    args = parser.parse_args()

    app = QGuiApplication(sys.argv[:1])
    engine = QQmlEngine()
    engine.addImageProvider("tagnan", LayerImages())
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "Tagnan.qml")))
    if component.isError():
        for error in component.errors():
            print(error.toString(), file=sys.stderr)
        return 1
    window = QQuickWindow()
    window.setColor(QColor("#E4E8F0" if args.light else "#1D2433"))
    window.resize(FIGURE_W, FIGURE_H)
    keep: list[object] = []  # Python references to what QML holds, or it segfaults
    sheet = QImage(
        FIGURE_W * len(args.at), FIGURE_H * len(args.grades), QImage.Format.Format_ARGB32
    )
    painter = QPainter(sheet)
    for row, grade in enumerate(args.grades):
        animator = Animator(Rig(), grade)
        spec = art.figure(grade)
        keep += [animator, spec]
        item = component.createWithInitialProperties({"animator": animator, "spec": spec})
        if not isinstance(item, QQuickItem):
            for error in component.errors():
                print(error.toString(), file=sys.stderr)
            return 1
        item.setParentItem(window.contentItem())
        item.setWidth(FIGURE_W)
        item.setHeight(FIGURE_H)
        window.show()
        animator.advance(0.5)
        animator.mood = args.mood
        for _ in range(args.tap):
            animator.tap()
            animator.advance(0.05)
        elapsed = 0.0
        for col, moment in enumerate(args.at):
            animator.advance(moment - elapsed)
            elapsed = moment
            app.processEvents()
            frame = window.grabWindow()
            painter.drawImage(col * FIGURE_W, row * FIGURE_H, frame)
        item.setVisible(False)
        item.deleteLater()
    painter.end()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    return 0 if sheet.save(str(args.out)) else 1


if __name__ == "__main__":
    sys.exit(main())
