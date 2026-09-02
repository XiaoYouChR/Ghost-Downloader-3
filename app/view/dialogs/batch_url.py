from __future__ import annotations

import re
from itertools import product
from string import ascii_lowercase, ascii_uppercase

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    CaptionLabel, FluentIcon, MessageBoxBase,
    SubtitleLabel, TeachingTip, TeachingTipTailPosition,
    TransparentToolButton,
)

from app.view.components.editors import AutoSizingEdit

RANGE_PATTERN = re.compile(r"\[([^\]]+)\]")
LIST_PATTERN = re.compile(r"\{([^}]+)\}")
TOKEN_PATTERN = re.compile(r"(\[[^\]]+\]|\{[^}]+\})")


def expandTemplate(template: str) -> list[str]:
    tokens = TOKEN_PATTERN.split(template)
    if len(tokens) == 1:
        return [template] if template.strip() else []

    segments: list[list[str]] = []
    for token in tokens:
        m_list = LIST_PATTERN.fullmatch(token)
        if m_list:
            segments.append([v.strip() for v in m_list.group(1).split(",") if v.strip()])
            continue

        m_range = RANGE_PATTERN.fullmatch(token)
        if m_range:
            values = _expandRange(m_range.group(1))
            if values is not None:
                segments.append(values)
                continue

        segments.append([token])

    return ["".join(combo) for combo in product(*segments)]


def _expandRange(spec: str) -> list[str] | None:
    parts = spec.split(":")
    if len(parts) > 2:
        return None

    rangePart = parts[0]
    step = 1
    if len(parts) == 2:
        try:
            step = int(parts[1])
        except ValueError:
            return None
        if step < 1:
            return None

    halves = rangePart.split("-", 1)
    if len(halves) != 2:
        return None

    start, end = halves[0].strip(), halves[1].strip()
    if not start or not end:
        return None

    if start.isdigit() and end.isdigit():
        width = len(start) if start[0] == "0" and len(start) > 1 else 0
        s, e = int(start), int(end)
        if s > e:
            return None
        return [str(i).zfill(width) for i in range(s, e + 1, step)]

    if len(start) == 1 and len(end) == 1 and start.isalpha() and end.isalpha():
        if start.islower() and end.islower():
            alphabet = ascii_lowercase
        elif start.isupper() and end.isupper():
            alphabet = ascii_uppercase
        else:
            return None
        si, ei = alphabet.index(start), alphabet.index(end)
        if si > ei:
            return None
        return list(alphabet[si:ei + 1:step])

    return None


class BatchUrlDialog(MessageBoxBase):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._urls: list[str] = []
        self._expandTimer = QTimer(self, singleShot=True)

        self.titleLabel = SubtitleLabel(self.tr("批量添加"), self)
        self.helpButton = TransparentToolButton(FluentIcon.QUESTION, self)
        self.titleRow = QHBoxLayout()
        self.templateEdit = AutoSizingEdit(self, minimumVisibleLines=2, maximumVisibleLines=3)
        self.previewEdit = AutoSizingEdit(self, minimumVisibleLines=3, maximumVisibleLines=12)
        self.countLabel = CaptionLabel("", self)

        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.widget.setFixedWidth(600)
        self.templateEdit.setPlaceholderText(
            self.tr("http://example.com/img/[001-100].jpg\n"
                     "http://example.com/{mp4,mkv}/video")
        )
        self.previewEdit.setReadOnly(True)
        self.previewEdit.setPlaceholderText(self.tr("输入模板后在此预览"))
        self.countLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.countLabel.setTextColor("grey", "grey")
        self.countLabel.hide()
        self.yesButton.setEnabled(False)

    def _initLayout(self) -> None:
        self.titleRow.addWidget(self.titleLabel)
        self.titleRow.addWidget(self.helpButton)
        self.titleRow.addStretch(1)
        self.titleRow.setContentsMargins(0, 0, 0, 0)

        self.viewLayout.addLayout(self.titleRow)
        self.viewLayout.addWidget(self.templateEdit)
        self.viewLayout.addWidget(self.previewEdit)
        self.viewLayout.addWidget(self.countLabel)
        self.viewLayout.setSpacing(8)
        self.viewLayout.setContentsMargins(24, 24, 24, 8)

    def _bind(self) -> None:
        self._expandTimer.setInterval(300)
        self._expandTimer.timeout.connect(self._onExpandNeeded)
        self.templateEdit.textChanged.connect(self._expandTimer.start)
        self.helpButton.clicked.connect(self._onHelpClicked)

    def urls(self) -> list[str]:
        return list(self._urls)

    def _onHelpClicked(self) -> None:
        TeachingTip.create(
            self.helpButton,
            self.tr("语法说明"),
            self.tr(
                "[1-100] → 1, 2, 3, …, 100\n"
                "[001-050] → 001, 002, …, 050 (自动补零)\n"
                "[1-10:2] → 1, 3, 5, 7, 9 (步长)\n"
                "[a-z] → a, b, …, z (字母范围)\n"
                "{mp4,mkv,avi} → mp4, mkv, avi (枚举)"
            ),
            tailPosition=TeachingTipTailPosition.BOTTOM,
            isClosable=True,
            duration=-1,
            parent=self,
        )

    def _onExpandNeeded(self) -> None:
        template = self.templateEdit.toPlainText().strip()
        if not template:
            self._urls = []
            self.previewEdit.clear()
            self.countLabel.hide()
            self.yesButton.setEnabled(False)
            return

        self._urls = expandTemplate(template)
        count = len(self._urls)
        self.yesButton.setEnabled(count > 0)

        if count == 0:
            self.previewEdit.clear()
            self.countLabel.hide()
        else:
            lines = self._urls[:10]
            if count > 10:
                lines.append("⋯")
                lines.append(self._urls[-1])
            self.previewEdit.setPlainText("\n".join(lines))
            self.countLabel.setText(self.tr("共 {} 个链接").format(count))
            self.countLabel.show()
