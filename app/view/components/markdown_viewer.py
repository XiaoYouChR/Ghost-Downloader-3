import re

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import (
    QBrush, QColor, QDesktopServices, QGuiApplication, QPainter, QPalette, QPixmap,
    QTextCursor, QTextDocument, QTextFrameFormat, QTextLength,
    QTextTableCellFormat, QTextTableFormat,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QSizePolicy
from qfluentwidgets import TextBrowser, isDarkTheme, themeColor


class MarkdownViewer(TextBrowser):

    ALERT_MARKER = re.compile(r"^\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*")
    ALERT_BLOCK = re.compile(
        r"^[ \t]*>[ \t]*\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\].*(?:\n[ \t]*>.*)*",
        re.MULTILINE,
    )
    ALERT_SPECS = {
        "note": (
            "#0969da", "#2f81f7",
            "M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.5 "
            "7.75A.75.75 0 0 1 7.25 7h1a.75.75 0 0 1 .75.75v2.75h.25a.75.75 0 0 1 0 1.5h-2a.75.75 "
            "0 0 1 0-1.5h.25v-2h-.25a.75.75 0 0 1-.75-.75ZM8 6a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z",
        ),
        "tip": (
            "#1a7f37", "#3fb950",
            "M8 1.5c-2.363 0-4 1.69-4 3.75 0 .984.424 1.625.984 2.304l.214.253c.223.264.47.556.673."
            "848.284.411.537.896.621 1.49a.75.75 0 0 1-1.484.211c-.04-.282-.163-.547-.37-.847a8.456 "
            "8.456 0 0 0-.542-.68c-.084-.1-.173-.205-.268-.32C3.201 7.75 2.5 6.766 2.5 5.25 2.5 2.31 "
            "4.863 0 8 0c3.137 0 5.5 2.31 5.5 5.25 0 1.516-.701 2.5-1.358 3.29-.095.115-.184.22-.268."
            "319-.207.245-.383.453-.541.681-.208.3-.33.565-.37.847a.751.751 0 0 1-1.485-.212c.084-.593"
            ".337-1.078.621-1.489.203-.292.45-.584.673-.848.075-.088.147-.173.213-.253.561-.679.985-"
            "1.32.985-2.304 0-2.06-1.637-3.75-4-3.75ZM5.75 12h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 "
            "1 0-1.5ZM6 15.25a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z",
        ),
        "important": (
            "#8250df", "#a371f7",
            "M0 1.75C0 .784.784 0 1.75 0h12.5C15.216 0 16 .784 16 1.75v9.5A1.75 1.75 0 0 1 14.25 "
            "13H8.06l-2.573 2.573A1.458 1.458 0 0 1 3 14.543V13H1.75A1.75 1.75 0 0 1 0 11.25Zm1.75-"
            ".25a.25.25 0 0 0-.25.25v9.5c0 .138.112.25.25.25h2a.75.75 0 0 1 .75.75v2.19l2.72-2.72a."
            "749.749 0 0 1 .53-.22h6.5a.25.25 0 0 0 .25-.25v-9.5a.25.25 0 0 0-.25-.25Zm7 2.25v2.5a."
            "75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM8 9a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z",
        ),
        "warning": (
            "#9a6700", "#d29922",
            "M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0 1 14.082 "
            "15H1.918a1.75 1.75 0 0 1-1.543-2.575Zm1.763.707a.25.25 0 0 0-.44 0L1.698 13.132a.25.25 "
            "0 0 0 .22.368h12.164a.25.25 0 0 0 .22-.368Zm.53 3.996v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 "
            "0 0 1 1.5 0ZM9 11a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z",
        ),
        "caution": (
            "#cf222e", "#f85149",
            "M4.47.22A.749.749 0 0 1 5 0h6c.199 0 .389.079.53.22l4.25 4.25c.141.14.22.331.22.53v6a."
            "749.749 0 0 1-.22.53l-4.25 4.25A.749.749 0 0 1 11 16H5a.749.749 0 0 1-.53-.22L.22 "
            "11.53A.749.749 0 0 1 0 11V5c0-.199.079-.389.22-.53Zm.84 1.28L1.5 5.31v5.38l3.81 "
            "3.81h5.38l3.81-3.81V5.31L10.69 1.5ZM8 4a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-"
            "3.5A.75.75 0 0 1 8 4Zm0 8a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z",
        ),
    }

    def __init__(self, parent=None, *, minimumVisibleLines: int = 5,
                 maximumVisibleLines: int | None = None) -> None:
        super().__init__(parent)
        self._minimumVisibleLines = minimumVisibleLines
        self._maximumVisibleLines = maximumVisibleLines

        self._initWidget()
        self._bind()

    def _initWidget(self) -> None:
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Link, themeColor())
        self.setPalette(palette)

    def _bind(self) -> None:
        self.document().contentsChanged.connect(self.updateGeometry)
        self.anchorClicked.connect(QDesktopServices.openUrl)

    def setMarkdown(self, text: str) -> None:
        separated = self.ALERT_BLOCK.sub(lambda m: m.group(0) + "\n\n<!-- -->", text)
        self.document().setMarkdown(separated)
        self._refreshAlertStyle()
        self.moveCursor(QTextCursor.MoveOperation.Start)  # 重置滚动位置到顶部

    def _refreshAlertStyle(self) -> None:
        isDark = isDarkTheme()
        titles = {
            "note": self.tr("Note"),
            "tip": self.tr("Tip"),
            "important": self.tr("Important"),
            "warning": self.tr("Warning"),
            "caution": self.tr("Caution"),
        }

        alerts: list[tuple[str, QTextCursor]] = []
        block = self.document().begin()
        while block.isValid():
            kind = self._matchAlert(block.text()) if block.blockFormat().leftMargin() > 0 else ""
            if kind:
                last = block
                following = block.next()
                while (
                    following.isValid()
                    and following.blockFormat().leftMargin() > 0
                    and not self._matchAlert(following.text())
                ):
                    last = following
                    following = following.next()
                cursor = QTextCursor(self.document())
                cursor.setPosition(block.position())
                cursor.setPosition(last.position() + last.length() - 1, QTextCursor.MoveMode.KeepAnchor)
                alerts.append((kind, cursor))
                block = following
                continue
            block = block.next()

        for kind, cursor in reversed(alerts):
            html = cursor.selection().toHtml()
            body = html.split("<!--StartFragment-->", 1)[1].split("<!--EndFragment-->", 1)[0]
            body = self.ALERT_MARKER.sub("", body, 1)
            body = re.sub(r'margin-left:\d+px;', '', body)
            body = f"<p>{body}</p>"
            cursor.removeSelectedText()
            light, dark, icon = self.ALERT_SPECS[kind]
            color = dark if isDark else light
            self._insertAlert(cursor, kind, color, icon, titles[kind], body)

    def _matchAlert(self, text: str) -> str:
        m = self.ALERT_MARKER.match(text)
        return m.group(1).lower() if m else ""

    def _insertAlert(self, cursor: QTextCursor, kind: str, color: str,
                     icon: str, title: str, body: str) -> None:
        tableFormat = QTextTableFormat()
        tableFormat.setBorder(0)
        tableFormat.setCellPadding(8)
        tableFormat.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
        cell = cursor.insertTable(1, 1, tableFormat).cellAt(0, 0)

        cellFormat = QTextTableCellFormat()
        cellFormat.setLeftBorder(4)
        cellFormat.setLeftBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        cellFormat.setLeftBorderBrush(QBrush(QColor(color)))
        cellFormat.setLeftPadding(12)
        cell.setFormat(cellFormat)

        self.document().addResource(
            QTextDocument.ResourceType.ImageResource,
            QUrl(f"alert:{kind}"),
            self._toAlertIcon(icon, color),
        )
        heading = (
            f'<p style="margin-top:0; margin-bottom:4px; color:{color};">'
            f'<img src="alert:{kind}" width="16" height="16" />&nbsp;<b>{title}</b></p>'
        )
        cell.firstCursorPosition().insertHtml(heading + body)

    def _toAlertIcon(self, icon: str, color: str, size: int = 16) -> QPixmap:
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="{color}">'
            f'<path fill-rule="evenodd" d="{icon}"/></svg>'
        )
        screen = QGuiApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen else 1.0
        pixmap = QPixmap(round(size * ratio), round(size * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, size, size))
        painter.end()
        return pixmap

    def _sizeForLines(self, count: int) -> QSize:
        margins = self.contentsMargins()
        viewportMargins = self.viewportMargins()
        padding = (
            margins.top() + margins.bottom()
            + viewportMargins.top() + viewportMargins.bottom()
            + self.frameWidth() * 2
            + round(self.document().documentMargin() * 2)
        )
        return QSize(super().sizeHint().width(),
                     padding + self.fontMetrics().lineSpacing() * count)

    def minimumSizeHint(self) -> QSize:
        return self._sizeForLines(self._minimumVisibleLines)

    def sizeHint(self) -> QSize:
        self.document().setTextWidth(max(0, self.viewport().width()))
        margins = self.contentsMargins()
        viewportMargins = self.viewportMargins()
        padding = (
            margins.top() + margins.bottom()
            + viewportMargins.top() + viewportMargins.bottom()
            + self.frameWidth() * 2
        )
        content = padding + round(self.document().size().height())
        height = max(self._sizeForLines(self._minimumVisibleLines).height(), content)
        if self._maximumVisibleLines is not None:
            height = min(height, self._sizeForLines(self._maximumVisibleLines).height())
        return QSize(super().sizeHint().width(), height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.updateGeometry()
