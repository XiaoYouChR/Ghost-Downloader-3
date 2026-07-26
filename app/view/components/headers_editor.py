from shlex import split as splitShellTokens
from typing import Final

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QValidator
from PySide6.QtWidgets import (
    QApplication, QCompleter, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    FluentIcon, LineEdit, TeachingTip, TeachingTipTailPosition, ToolTipFilter,
    TransparentToolButton,
)

from app.view.components.editors import AutoSizingEdit


CURL_HEADER_FLAGS: Final[frozenset[str]] = frozenset({"-H", "--header"})
COMMAND_SEPARATORS: Final[frozenset[str]] = frozenset({";", "&", "&&", "|", "||"})
CURL_VALUE_FLAGS: Final[dict[str, str]] = {
    "-b": "cookie", "--cookie": "cookie",
    "-A": "user-agent", "--user-agent": "user-agent",
    "-e": "referer", "--referer": "referer",
}


def toLogicalLines(text: str) -> list[str]:
    merged = text.replace("\r\n", "\n").replace("\\\n", " ").replace("^\n", " ")
    return [line.strip() for line in merged.splitlines() if line.strip()]


def parseHeaderLine(line: str) -> tuple[str, str] | None:
    name, separator, value = line.partition(":")
    name = name.strip()
    # 名称为空是 HTTP/2 伪头，含空白是请求行——两者都不是标头，原样发出去会破坏请求
    if not separator or not name or any(char.isspace() for char in name):
        return None
    return name, value.strip()


def parseCurl(line: str) -> list[tuple[str, str]]:
    try:
        tokens = splitShellTokens(line.replace("$'", "'"))
    except ValueError:
        return []

    rows: list[tuple[str, str]] = []
    index = 1
    while index < len(tokens) - 1:
        token = tokens[index]
        # Windows 的「复制全部为 cURL」把多条命令用 & 连在同一行，到此为止
        if token in COMMAND_SEPARATORS:
            break
        if token in CURL_HEADER_FLAGS:
            row = parseHeaderLine(tokens[index + 1])
            if row:
                rows.append(row)
        elif token in CURL_VALUE_FLAGS:
            rows.append((CURL_VALUE_FLAGS[token], tokens[index + 1].strip()))
        else:
            index += 1
            continue
        index += 2
    return rows


def parseHeaders(text: str) -> list[tuple[str, str]]:
    # 逐行分派而非整段二选一，否则 cURL 后面手加的裸行会被静默吞掉
    rows: list[tuple[str, str]] = []
    hasCurl = False
    for line in toLogicalLines(text):
        if line[:5].lower() == "curl ":
            # 一份标头属于一个请求。「复制全部为 cURL」是多个请求，
            # 混在一起产出的标头集不对应任何一个真实请求，所以只认第一条。
            if hasCurl:
                continue
            hasCurl = True
            rows.extend(parseCurl(line))
            continue
        row = parseHeaderLine(line)
        if row:
            rows.append(row)
    return rows


def toHeadersText(rows: list[tuple[str, str]]) -> str:
    return "\n".join(f"{name}: {value}" if value else name for name, value in rows)


def toHeaderRows(text: str) -> list[tuple[str, str]]:
    # 字面切分、零丢弃——视图切换必须无损，清洗只发生在粘贴时
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        name, separator, value = line.partition(":")
        rows.append((name.strip(), value.strip()) if separator else (line.strip(), ""))
    return rows


class HeaderNameValidator(QValidator):

    # 冒号会让「Key 含冒号」的行在视图往返时裂成两半，空白则是非法标头名
    def validate(self, text: str, pos: int):
        if ":" in text or any(char.isspace() for char in text):
            return QValidator.State.Invalid, text, pos
        return QValidator.State.Acceptable, text, pos


class HeaderCellEdit(LineEdit):

    def __init__(self, parent=None, *, isName: bool, onPaste):
        super().__init__(parent)
        self.isName = isName
        self._onPaste = onPaste

    # QLineEdit 的 Ctrl+V 不走 paste()，右键菜单走——两条路都收敛到这里
    def paste(self) -> None:
        if self._onPaste(self, QApplication.clipboard().text()):
            return
        super().paste()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste()
            return
        super().keyPressEvent(event)


HEADER_SUGGESTIONS: Final[list[str]] = [
    "accept", "accept-encoding", "accept-language", "authorization",
    "cache-control", "cookie", "origin", "range", "referer", "user-agent",
]


class HeaderRow(QWidget):

    def __init__(self, parent=None, *, name: str = "", value: str = "",
                 onPaste, onEdited, onRemoved):
        super().__init__(parent)
        self._name = name
        self._value = value
        self._onEdited = onEdited
        self._onRemoved = onRemoved

        self.nameEdit = HeaderCellEdit(self, isName=True, onPaste=onPaste)
        self.valueEdit = HeaderCellEdit(self, isName=False, onPaste=onPaste)
        self.removeButton = TransparentToolButton(FluentIcon.CLOSE, self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        completer = QCompleter(HEADER_SUGGESTIONS, self.nameEdit)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.nameEdit.setCompleter(completer)
        self.nameEdit.setValidator(HeaderNameValidator(self.nameEdit))
        self.nameEdit.setPlaceholderText(self.tr("名称"))
        self.nameEdit.setText(self._name)

        self.valueEdit.setPlaceholderText(self.tr("值"))
        self.valueEdit.setText(self._value)

        self.removeButton.setFixedSize(24, 24)
        self.removeButton.setIconSize(QSize(10, 10))
        sizePolicy = self.removeButton.sizePolicy()
        sizePolicy.setRetainSizeWhenHidden(True)
        self.removeButton.setSizePolicy(sizePolicy)
        self.removeButton.setVisible(bool(self._name or self._value))

    def _initLayout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.nameEdit, 2)  # 名称列窄、值列宽
        layout.addWidget(self.valueEdit, 3)
        layout.addWidget(self.removeButton)

    # 文本在 _initWidget 里填完才接信号，批量填充与粘贴因此不会级联触发
    def _bind(self) -> None:
        self.nameEdit.textChanged.connect(self._onTextChanged)
        self.valueEdit.textChanged.connect(self._onTextChanged)
        self.removeButton.clicked.connect(lambda: self._onRemoved(self))

    def header(self) -> tuple[str, str]:
        return self.nameEdit.text(), self.valueEdit.text()

    def setDuplicate(self, isDuplicate: bool) -> None:
        self.nameEdit.setError(isDuplicate)

    def _onTextChanged(self) -> None:
        # 一旦非空就露出删除按钮，之后不再收回——清空内容后仍要能删掉这一行
        if any(text.strip() for text in self.header()):
            self.removeButton.show()
        self._onEdited(self)


class HeadersTextEdit(AutoSizingEdit):

    def insertFromMimeData(self, source) -> None:
        rows = parseHeaders(source.text())
        if not rows:
            super().insertFromMimeData(source)
            return
        self.insertPlainText(toHeadersText(rows))


class HeadersEditor(QWidget):

    def __init__(self, parent=None, *, defaults: dict[str, str]):
        super().__init__(parent)
        self._defaults = dict(defaults)
        self._isTextMode = False

        self.toolbar = QWidget(self)
        self.helpButton = TransparentToolButton(FluentIcon.QUESTION, self.toolbar)
        self.modeButton = TransparentToolButton(FluentIcon.ALIGNMENT, self.toolbar)
        self.resetButton = TransparentToolButton(FluentIcon.SYNC, self.toolbar)
        self.table = QWidget(self)
        self.textEdit = HeadersTextEdit(self, minimumVisibleLines=4, maximumVisibleLines=12)

        self.vBoxLayout = QVBoxLayout(self)
        self.tableLayout = QVBoxLayout(self.table)
        self.toolbarLayout = QHBoxLayout(self.toolbar)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.textEdit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.textEdit.hide()
        self.textEdit.setPlaceholderText(
            self.tr("每行一个 名称: 值，或直接粘贴 cURL 命令"))
        self.helpButton.setToolTip(self.tr("请求标头帮助"))
        self.modeButton.setToolTip(self.tr("切换到文本视图"))
        self.resetButton.setToolTip(self.tr("恢复默认请求标头"))
        for button in (self.helpButton, self.modeButton, self.resetButton):
            button.installEventFilter(ToolTipFilter(button))

    def _initLayout(self) -> None:
        self.toolbarLayout.setContentsMargins(0, 0, 0, 0)
        self.toolbarLayout.setSpacing(4)
        self.toolbarLayout.addWidget(self.helpButton)
        self.toolbarLayout.addWidget(self.modeButton)
        self.toolbarLayout.addWidget(self.resetButton)

        self.tableLayout.setContentsMargins(0, 0, 0, 0)
        self.tableLayout.setSpacing(4)

        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.addWidget(self.table)
        self.vBoxLayout.addWidget(self.textEdit)

    def _bind(self) -> None:
        self.helpButton.clicked.connect(self._onHelpClicked)
        self.modeButton.clicked.connect(self._onModeToggled)
        self.resetButton.clicked.connect(self.reset)

    def headers(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, value in self._currentRows():
            key = name.strip().lower()
            value = value.strip()
            if key and value:
                result[key] = value
        return result

    def setHeaders(self, headers: dict[str, str]) -> None:
        self._setRows(list(headers.items()))

    def reset(self) -> None:
        self.setHeaders(self._defaults)

    # 行的顺序只有 tableLayout 一个所有者，不另存一份列表
    def _rows(self) -> list[HeaderRow]:
        return [self.tableLayout.itemAt(i).widget()
                for i in range(self.tableLayout.count())]

    def _lastRow(self) -> HeaderRow:
        return self.tableLayout.itemAt(self.tableLayout.count() - 1).widget()

    def _currentRows(self) -> list[tuple[str, str]]:
        if self._isTextMode:
            return toHeaderRows(self.textEdit.toPlainText())
        return [row.header() for row in self._rows() if any(row.header())]

    def _setRows(self, rows: list[tuple[str, str]]) -> None:
        if self._isTextMode:
            self.textEdit.setPlainText(toHeadersText(rows))
            return
        self._clearRows()
        for name, value in rows:
            self._addRow(name, value)
        self._addRow()
        self._refreshDuplicates()

    def _onModeToggled(self) -> None:
        rows = self._currentRows()
        self._isTextMode = not self._isTextMode
        self.table.setVisible(not self._isTextMode)
        self.textEdit.setVisible(self._isTextMode)
        self.modeButton.setToolTip(
            self.tr("切换到表格视图") if self._isTextMode else self.tr("切换到文本视图"))
        self._setRows(rows)

    def _onHelpClicked(self) -> None:
        TeachingTip.create(
            self.helpButton,
            self.tr("请求标头"),
            self.tr(
                "直接粘贴即可识别：\n"
                "  cURL 命令（浏览器开发者工具的 Copy as cURL）\n"
                "  名称: 值（每行一个）\n"
                "\n"
                "一份标头属于一个请求。粘贴「复制全部为 cURL」时，"
                "只取第一个请求的标头。\n"
                "\n"
                "开启「模拟身份」时，User-Agent 与 sec-ch-ua 可能由模拟身份接管。"
                "要让这里填写的值原样发送，请将模拟身份设为「不模拟」。"
            ),
            tailPosition=TeachingTipTailPosition.BOTTOM,
            isClosable=True,
            duration=-1,
            parent=self,
        )

    def _onPaste(self, edit: HeaderCellEdit, text: str) -> bool:
        # 换行在标头名与标头值里都非法，所以含换行的粘贴一定不是「填这一格」的意图
        if "\n" not in text and "\r" not in text:
            if not edit.isName or edit.text():
                return False
        rows = parseHeaders(text)
        if not rows:
            return False
        index = self.tableLayout.indexOf(edit.parentWidget())
        for offset, (name, value) in enumerate(rows):
            self._addRow(name, value, index + offset)
        self._refreshDuplicates()
        return True

    def _addRow(self, name: str = "", value: str = "", index: int | None = None) -> None:
        row = HeaderRow(self.table, name=name, value=value, onPaste=self._onPaste,
                        onEdited=self._onRowEdited, onRemoved=self._removeRow)
        self.tableLayout.insertWidget(
            self.tableLayout.count() if index is None else index, row)

    def _onRowEdited(self, row: HeaderRow) -> None:
        if row is self._lastRow() and any(text.strip() for text in row.header()):
            self._addRow()
        self._refreshDuplicates()

    def _removeRow(self, row: HeaderRow) -> None:
        if row is self._lastRow():
            return
        # setParent(None) 让它立刻退出布局，deleteLater 要等到事件循环才生效
        row.setParent(None)
        row.deleteLater()
        self._refreshDuplicates()

    def _clearRows(self) -> None:
        for row in self._rows():
            row.setParent(None)
            row.deleteLater()

    def _refreshDuplicates(self) -> None:
        seen: set[str] = set()
        for row in self._rows():
            name = row.header()[0].strip().lower()
            row.setDuplicate(name in seen)
            if name:
                seen.add(name)
