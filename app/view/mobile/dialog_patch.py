def patchFileDialogs() -> None:
    from urllib.parse import unquote

    from PySide6.QtWidgets import QFileDialog

    def toRealPath(uri: str) -> str:
        if not uri:
            return uri
        if uri.startswith("file://"):
            return unquote(uri[len("file://"):])
        if not uri.startswith("content://"):
            return uri
        for marker in ("/tree/", "/document/"):
            index = uri.find(marker)
            if index < 0:
                continue
            documentId = unquote(uri[index + len(marker):])
            volume, separator, relative = documentId.partition(":")
            if not separator:
                return uri
            base = "/storage/emulated/0" if volume == "primary" else f"/storage/{volume}"
            return f"{base}/{relative}" if relative else base
        return uri

    originalDirectory = QFileDialog.getExistingDirectory
    originalOpenFiles = QFileDialog.getOpenFileNames

    def resolveExistingDirectory(*args, **kwargs) -> str:
        return toRealPath(originalDirectory(*args, **kwargs))

    def resolveOpenFileNames(*args, **kwargs):
        paths, selectedFilter = originalOpenFiles(*args, **kwargs)
        return [toRealPath(path) for path in paths], selectedFilter

    QFileDialog.getExistingDirectory = staticmethod(resolveExistingDirectory)
    QFileDialog.getOpenFileNames = staticmethod(resolveOpenFileNames)

def patchMessageBoxWidth() -> None:
    from qfluentwidgets import MessageBoxBase

    originalShowEvent = MessageBoxBase.showEvent

    def showEventWithWidthLimit(self, event):
        parent = self.parent()
        if parent is not None:
            widthLimit = parent.width() - 24
            if 0 < widthLimit < self.widget.width():
                self.widget.setFixedWidth(widthLimit)
        originalShowEvent(self, event)

    MessageBoxBase.showEvent = showEventWithWidthLimit
