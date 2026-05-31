from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound


def toHighlightedHtml(code: str, lang: str, style: str) -> str:
    try:
        lexer = get_lexer_by_name(lang) if lang else guess_lexer(code)
    except ClassNotFound:
        lexer = TextLexer()
    formatter = HtmlFormatter(style=style, nowrap=True, noclasses=True)
    inner = highlight(code, lexer, formatter)
    return (
        '<pre style="margin:0; white-space:pre;'
        " font-family:Consolas,'Courier New',monospace;\">"
        f"{inner}</pre>"
    )


class CodeBlock(QWidget):
    def __init__(self, code: str, lang: str, codeStyle: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._code = code
        self._lang = lang
        self._codeStyle = codeStyle
        # instant widget
        self._langLabel = QLabel(lang)
        self._copyButton = QToolButton()
        self._editor = QTextEdit()
        # instant layout
        self._headerLayout = QHBoxLayout()
        self._rootLayout = QVBoxLayout(self)
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.setObjectName("code-block")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._langLabel.setObjectName("code-lang")
        self._copyButton.setObjectName("code-copy")
        self._copyButton.setText("Copy")
        self._copyButton.setCursor(Qt.PointingHandCursor)
        self._editor.setObjectName("code-editor")
        self._editor.setReadOnly(True)
        self._editor.setFrameShape(QFrame.NoFrame)
        self._editor.setLineWrapMode(QTextEdit.NoWrap)
        self._editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._editor.setHtml(toHighlightedHtml(self._code, self._lang, self._codeStyle))
        # Code blocks grow with content rather than scrolling vertically (GitHub behaviour).
        self._editor.document().setDocumentMargin(10)
        height = int(self._editor.document().size().height())
        self._editor.setFixedHeight(height + 18)

    def _initLayout(self) -> None:
        self._headerLayout.setContentsMargins(10, 4, 6, 4)
        self._headerLayout.addWidget(self._langLabel)
        self._headerLayout.addStretch(1)
        self._headerLayout.addWidget(self._copyButton)
        self._rootLayout.setContentsMargins(0, 0, 0, 0)
        self._rootLayout.setSpacing(0)
        self._rootLayout.addLayout(self._headerLayout)
        self._rootLayout.addWidget(self._editor)

    def _bind(self) -> None:
        self._copyButton.clicked.connect(self.onCopyClicked)

    def onCopyClicked(self) -> None:
        QApplication.clipboard().setText(self._code)
