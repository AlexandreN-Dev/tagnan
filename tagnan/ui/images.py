"""image://tagnan/<grade>/<layer>/<expression>: Tagnan's SVG layers (tagnan.art), rendered by QtSvg
at the size QML asks for, that is at the screen's own resolution."""

from PySide6.QtCore import QByteArray, QRectF, QSize
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

from tagnan import art


def render_svg(svg: str, width: int, height: int) -> QImage:
    image = QImage(max(width, 1), max(height, 1), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter, QRectF(0, 0, image.width(), image.height()))
    painter.end()
    return image


class LayerImages(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, id: str, size: QSize, requestedSize: QSize) -> QImage:
        try:
            stage_text, name, expression = id.split("/")
            stage = int(stage_text)
        except ValueError:
            return QImage()
        if name == "still":  # his menu's header: the icon of his grade
            svg: str | None = art.icon_svg(stage)
        elif name == "silhouette":  # the whole figure in white, as he evolves (Tagnan.qml)
            svg = art.still_svg(stage, glow=False, shadow=False)
        else:
            svg = art.layer(stage, name, "idle" if expression == "-" else expression)
        box_w, box_h = (
            (art.RAPIER_BOX[2], art.RAPIER_BOX[3]) if name == "rapier" else (art.WIDTH, art.HEIGHT)
        )
        width = requestedSize.width() if requestedSize.width() > 0 else round(box_w)
        height = requestedSize.height() if requestedSize.height() > 0 else round(box_h)
        image = (
            render_svg(svg, width, height)
            if svg
            else QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
        )
        if svg is None:
            image.fill(QColor(0, 0, 0, 0))
        elif name == "silhouette":
            # Solid, though the inkwell's glass lets light through: laid over itself a few times.
            once = image.copy()
            painter = QPainter(image)
            for _ in range(12):
                painter.drawImage(0, 0, once)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(image.rect(), QColor("white"))
            painter.end()
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image
