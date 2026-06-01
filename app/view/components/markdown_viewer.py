import re

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QGuiApplication,
    QPainter,
    QPixmap,
    QTextCursor,
    QTextDocument,
    QTextFrameFormat,
    QTextLength,
    QTextTableCellFormat,
    QTextTableFormat,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QSizePolicy
from qfluentwidgets import TextBrowser
from qfluentwidgets.common.icon import isDarkTheme

_ALERT_MARKER_RE = re.compile(r"^\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*")
# 引用缩进要全去掉:callout 的 cell 已经是容器了
_BLOCKQUOTE_INDENT_RE = re.compile(r"margin-left:\d+px;")
_ALERT_BLOCK_RE = re.compile(
    r"^[ \t]*>[ \t]*\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\].*(?:\n[ \t]*>.*)*",
    re.MULTILINE,
)

# GitHub 官方 octicon 路径;颜色在渲染时按主题注入,与色条、标题同源。
_OCTICONS = {
    "note": (
        "M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.5 "
        "7.75A.75.75 0 0 1 7.25 7h1a.75.75 0 0 1 .75.75v2.75h.25a.75.75 0 0 1 0 1.5h-2a.75.75 "
        "0 0 1 0-1.5h.25v-2h-.25a.75.75 0 0 1-.75-.75ZM8 6a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z"
    ),
    "tip": (
        "M8 1.5c-2.363 0-4 1.69-4 3.75 0 .984.424 1.625.984 2.304l.214.253c.223.264.47.556.673."
        "848.284.411.537.896.621 1.49a.75.75 0 0 1-1.484.211c-.04-.282-.163-.547-.37-.847a8.456 "
        "8.456 0 0 0-.542-.68c-.084-.1-.173-.205-.268-.32C3.201 7.75 2.5 6.766 2.5 5.25 2.5 2.31 "
        "4.863 0 8 0c3.137 0 5.5 2.31 5.5 5.25 0 1.516-.701 2.5-1.358 3.29-.095.115-.184.22-.268."
        "319-.207.245-.383.453-.541.681-.208.3-.33.565-.37.847a.751.751 0 0 1-1.485-.212c.084-.593"
        ".337-1.078.621-1.489.203-.292.45-.584.673-.848.075-.088.147-.173.213-.253.561-.679.985-"
        "1.32.985-2.304 0-2.06-1.637-3.75-4-3.75ZM5.75 12h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 "
        "1 0-1.5ZM6 15.25a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z"
    ),
    "important": (
        "M0 1.75C0 .784.784 0 1.75 0h12.5C15.216 0 16 .784 16 1.75v9.5A1.75 1.75 0 0 1 14.25 "
        "13H8.06l-2.573 2.573A1.458 1.458 0 0 1 3 14.543V13H1.75A1.75 1.75 0 0 1 0 11.25Zm1.75-"
        ".25a.25.25 0 0 0-.25.25v9.5c0 .138.112.25.25.25h2a.75.75 0 0 1 .75.75v2.19l2.72-2.72a."
        "749.749 0 0 1 .53-.22h6.5a.25.25 0 0 0 .25-.25v-9.5a.25.25 0 0 0-.25-.25Zm7 2.25v2.5a."
        "75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM8 9a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z"
    ),
    "warning": (
        "M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0 1 14.082 "
        "15H1.918a1.75 1.75 0 0 1-1.543-2.575Zm1.763.707a.25.25 0 0 0-.44 0L1.698 13.132a.25.25 "
        "0 0 0 .22.368h12.164a.25.25 0 0 0 .22-.368Zm.53 3.996v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 "
        "0 0 1 1.5 0ZM9 11a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"
    ),
    "caution": (
        "M4.47.22A.749.749 0 0 1 5 0h6c.199 0 .389.079.53.22l4.25 4.25c.141.14.22.331.22.53v6a."
        "749.749 0 0 1-.22.53l-4.25 4.25A.749.749 0 0 1 11 16H5a.749.749 0 0 1-.53-.22L.22 "
        "11.53A.749.749 0 0 1 0 11V5c0-.199.079-.389.22-.53Zm.84 1.28L1.5 5.31v5.38l3.81 "
        "3.81h5.38l3.81-3.81V5.31L10.69 1.5ZM8 4a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-"
        "3.5A.75.75 0 0 1 8 4Zm0 8a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z"
    ),
}

_LIGHT_COLORS = {
    "note": "#0969da",
    "tip": "#1a7f37",
    "important": "#8250df",
    "warning": "#9a6700",
    "caution": "#cf222e",
}

_DARK_COLORS = {
    "note": "#2f81f7",
    "tip": "#3fb950",
    "important": "#a371f7",
    "warning": "#d29922",
    "caution": "#f85149",
}


def _alertPalette(isDark: bool) -> dict[str, str]:
    return _DARK_COLORS if isDark else _LIGHT_COLORS


def _matchAlert(text: str) -> str:
    match = _ALERT_MARKER_RE.match(text)
    return match.group(1).lower() if match else ""


def _separateAlerts(text: str) -> str:
    # Qt setMarkdown 不保留 blockquote 边界,紧邻的独立引用会和 alert 粘成一片;插个 HTML
    # 注释当分隔——它渲染成 leftMargin=0 的空 block,后处理就能认出 alert 在哪结束。
    return _ALERT_BLOCK_RE.sub(lambda m: m.group(0) + "\n\n<!-- -->", text)


def _toAlertBody(fragmentHtml: str) -> str:
    # Qt 把选区正文夹在 StartFragment/EndFragment 之间;跨 block 选区会切出半开的 <p>,外包一层配平。
    body = fragmentHtml.split("<!--StartFragment-->", 1)[1].split("<!--EndFragment-->", 1)[0]
    body = _ALERT_MARKER_RE.sub("", body, 1)
    return f"<p>{_BLOCKQUOTE_INDENT_RE.sub('', body)}</p>"


def _toAlertIcon(kind: str, color: str, size: int = 16) -> QPixmap:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="{color}">'
        f'<path fill-rule="evenodd" d="{_OCTICONS[kind]}"/></svg>'
    )
    screen = QGuiApplication.primaryScreen()
    ratio = screen.devicePixelRatio() if screen else 1.0
    pixmap = QPixmap(round(size * ratio), round(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    # 显式给逻辑尺寸的 rect,否则高分屏上 dpr 变换会二次缩放并裁切。
    QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


class MarkdownViewer(TextBrowser):
    """只读 GitHub markdown 查看器。正文交给 Qt 原生 setMarkdown,额外把 GitHub alert
    (> [!NOTE] 等)后处理成带色条 + octicon 的 callout;高度随内容自动伸缩,超出上限滚动。
    """

    def __init__(
        self,
        parent=None,
        minimumVisibleLines: int = 5,
        maximumVisibleLines: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._minimumVisibleLines = minimumVisibleLines
        self._maximumVisibleLines = maximumVisibleLines

        self._initWidget()
        self._bind()

    def _initWidget(self) -> None:
        self.setReadOnly(True)
        self.setOpenLinks(False)  # 链接交宿主用浏览器打开,不在控件内导航
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _bind(self) -> None:
        self.document().contentsChanged.connect(self.updateGeometry)
        self.anchorClicked.connect(QDesktopServices.openUrl)

    def setMarkdown(self, text: str) -> None:
        self.document().setMarkdown(_separateAlerts(text))
        self._styleAlerts()  # contentsChanged 已驱动 updateGeometry,无需再手动触发

    def _styleAlerts(self) -> None:
        palette = _alertPalette(isDarkTheme())
        titles = {
            "note": self.tr("Note"),
            "tip": self.tr("Tip"),
            "important": self.tr("Important"),
            "warning": self.tr("Warning"),
            "caution": self.tr("Caution"),
        }
        # 从后往前:Qt 保证编辑点之前的游标不偏移,预存的整段游标才一直有效。
        for kind, cursor in reversed(self._matchAlerts()):
            body = _toAlertBody(cursor.selection().toHtml())
            cursor.removeSelectedText()
            self._insertAlert(cursor, kind, palette[kind], titles[kind], body)

    def _insertAlert(self, cursor: QTextCursor, kind: str, color: str, title: str, body: str) -> None:
        tableFormat = QTextTableFormat()
        tableFormat.setBorder(0)  # 默认 1,要去掉外框
        tableFormat.setCellPadding(8)
        tableFormat.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
        cell = cursor.insertTable(1, 1, tableFormat).cellAt(0, 0)

        cellFormat = QTextTableCellFormat()
        cellFormat.setLeftBorder(4)  # 左色条:Qt 只认编程式分边边框,认不了 HTML/CSS
        cellFormat.setLeftBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        cellFormat.setLeftBorderBrush(QBrush(QColor(color)))
        cellFormat.setLeftPadding(12)
        cell.setFormat(cellFormat)

        self.document().addResource(
            QTextDocument.ResourceType.ImageResource, QUrl(f"alert:{kind}"), _toAlertIcon(kind, color)
        )
        title = (
            f'<p style="margin-top:0; margin-bottom:4px; color:{color};">'
            f'<img src="alert:{kind}" width="16" height="16" />&nbsp;<b>{title}</b></p>'
        )
        cell.firstCursorPosition().insertHtml(title + body)

    def _matchAlerts(self) -> list[tuple[str, QTextCursor]]:
        matches = []
        block = self.document().begin()
        while block.isValid():
            kind = _matchAlert(block.text()) if block.blockFormat().leftMargin() > 0 else ""
            if kind:
                last = block
                following = block.next()
                while (
                    following.isValid()
                    and following.blockFormat().leftMargin() > 0
                    and not _matchAlert(following.text())
                ):
                    last = following
                    following = following.next()
                cursor = QTextCursor(self.document())
                cursor.setPosition(block.position())
                cursor.setPosition(last.position() + last.length() - 1, QTextCursor.MoveMode.KeepAnchor)
                matches.append((kind, cursor))
                block = following
                continue
            block = block.next()
        return matches

    def _chromeHeight(self) -> int:
        margins = self.contentsMargins()
        viewportMargins = self.viewportMargins()
        return (
            margins.top()
            + margins.bottom()
            + viewportMargins.top()
            + viewportMargins.bottom()
            + self.frameWidth() * 2
        )

    def _heightForLines(self, lineCount: int) -> int:
        documentMargin = round(self.document().documentMargin() * 2)
        return self._chromeHeight() + documentMargin + self.fontMetrics().lineSpacing() * lineCount

    def minimumSizeHint(self) -> QSize:
        return QSize(super().minimumSizeHint().width(), self._heightForLines(self._minimumVisibleLines))

    def sizeHint(self) -> QSize:
        self.document().setTextWidth(max(0, self.viewport().width()))
        content = self._chromeHeight() + round(self.document().size().height())
        height = max(self._heightForLines(self._minimumVisibleLines), content)
        if self._maximumVisibleLines is not None:
            height = min(height, self._heightForLines(self._maximumVisibleLines))
        return QSize(super().sizeHint().width(), height)

    # sizeHint 依赖 viewport 宽度(富文本换行),宽度一变就得重新通告布局,否则拉宽后高度不收缩。
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.updateGeometry()
