"""Where catalogues come in and go out (tagnan.catalogue): the clipboard, where one's assistant's
answer was copied and where his prompts go; a file chosen in the system's own dialog; Downloads,
where an export is written. The controller's tests give it places of their own."""

from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog

from tagnan import catalogue
from tagnan.ui import sheetpdf


class Files:
    def text(self) -> str:
        """What the clipboard holds, as text."""
        return QGuiApplication.clipboard().text()

    def copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    def choose(self) -> Path | None:
        """A catalogue to import, chosen in the system's Open dialog, from Downloads."""
        found, _ = QFileDialog.getOpenFileName(
            None,
            "Import a catalogue",
            str(sheetpdf.downloads()),
            "Catalogues (*.json);;All files (*)",
        )
        return Path(found) if found else None

    def read(self, path: Path) -> str:
        """A file's text; OSError, or ValueError for one far too big to be a catalogue."""
        if path.stat().st_size > catalogue.MAX_CHARS:
            raise ValueError("it is too big for a catalogue")
        return path.read_text(encoding="utf-8-sig")

    def write(self, data: dict[str, object], name: str) -> Path:
        """An export, in Downloads, next to nothing it would replace."""
        return catalogue.write(data, sheetpdf.downloads(), name)

    def show(self, path: Path) -> None:
        """Its folder, the file selected."""
        sheetpdf.show_in_folder(path)
