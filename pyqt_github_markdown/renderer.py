import html
import re

from markdown_it.tree import SyntaxTreeNode
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QLabel, QWidget

from pyqt_github_markdown.blocks import (
    BlockQuote,
    CodeBlock,
    ImagePlaceholder,
    ListBlock,
    ListItem,
    TableBlock,
)
from pyqt_github_markdown.icons import toAlertIcon
from pyqt_github_markdown.inline import inlineHtmlOf
from pyqt_github_markdown.theme import Theme

_TASK_RE = re.compile(r"^\s*\[([ xX])\]\s+")
_ALERT_RE = re.compile(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]")
_ALERT_STRIP_RE = re.compile(r"^\s*\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*")


def _leadingText(node: SyntaxTreeNode) -> str:
    # First text run of a container's first paragraph — enough to spot task/alert markers.
    for child in node.children:
        if child.type == "paragraph" and child.children:
            for token in child.children[0].children:
                if token.type == "text":
                    return token.content
            return ""
    return ""


def _setupTextLabel(label: QLabel) -> None:
    label.setTextFormat(Qt.RichText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)


def _cellAlign(cell: SyntaxTreeNode) -> Qt.AlignmentFlag:
    style = cell.attrs.get("style", "")
    if "center" in style:
        return Qt.AlignHCenter
    if "right" in style:
        return Qt.AlignRight
    return Qt.AlignLeft


class MarkdownRenderer:
    def buildDocument(self, tree: SyntaxTreeNode, theme: Theme) -> list[QWidget]:
        return [w for node in tree.children if (w := self._buildBlock(node, theme))]

    def _buildBlock(self, node: SyntaxTreeNode, theme: Theme) -> QWidget | None:
        match node.type:
            case "heading":
                return self.buildHeading(node, theme)
            case "paragraph":
                return self.buildParagraph(node, theme)
            case "fence" | "code_block":
                lang = node.info.split()[0] if node.info else ""
                return CodeBlock(node.content, lang, theme.codeStyle)
            case "blockquote":
                return self.buildBlockQuote(node, theme)
            case "bullet_list" | "ordered_list":
                return self.buildList(node, theme)
            case "table":
                return self.buildTable(node, theme)
            case "hr":
                return self._buildRule()
            case "html_block":
                return self.buildParagraph(node, theme, escaped=node.content)
            case _:
                return None

    def buildHeading(self, node: SyntaxTreeNode, theme: Theme) -> QLabel:
        label = QLabel(inlineHtmlOf(node, theme.inlineCode))
        label.setObjectName(node.tag)  # h1 .. h6
        _setupTextLabel(label)
        return label

    def buildParagraph(self, node: SyntaxTreeNode, theme: Theme, escaped: str = "") -> QWidget:
        if escaped:
            label = QLabel(html.escape(escaped))
            label.setObjectName("paragraph")
            _setupTextLabel(label)
            return label
        image = self._soleImage(node)
        if image is not None:
            return ImagePlaceholder(image.content, image.attrs.get("src", ""))
        label = QLabel(inlineHtmlOf(node, theme.inlineCode))
        label.setObjectName("paragraph")
        _setupTextLabel(label)
        return label

    def buildBlockQuote(self, node: SyntaxTreeNode, theme: Theme) -> BlockQuote:
        kind = self.matchAlert(node)
        children = [w for c in node.children if (w := self._buildBlock(c, theme))]
        if kind and children and isinstance(children[0], QLabel):
            # The "[!NOTE]" marker shares the first paragraph; the title row replaces it.
            stripped = _ALERT_STRIP_RE.sub("", children[0].text())
            if stripped.strip():
                children[0].setText(stripped)
            else:
                children = children[1:]
        if not kind:
            return BlockQuote(children, "quote")
        return BlockQuote(children, kind, toAlertIcon(kind, theme.alertColors[kind]))

    def buildList(self, node: SyntaxTreeNode, theme: Theme) -> ListBlock:
        ordered = node.type == "ordered_list"
        start = int(node.attrs.get("start", 1)) if ordered else 1
        items = [
            self.buildListItem(item, ordered, start + offset, theme)
            for offset, item in enumerate(node.children)
        ]
        return ListBlock(items)

    def buildListItem(
        self, node: SyntaxTreeNode, ordered: bool, number: int, theme: Theme
    ) -> ListItem:
        checked = self.matchTask(node)
        children = [w for c in node.children if (w := self._buildBlock(c, theme))]
        if checked is not None:
            if children and isinstance(children[0], QLabel):
                children[0].setText(_TASK_RE.sub("", children[0].text()))
            marker = self._taskBox(checked)
        elif ordered:
            marker = self._markerLabel(f"{number}.")
        else:
            marker = self._markerLabel("•")
        return ListItem(marker, children)

    def buildTable(self, node: SyntaxTreeNode, theme: Theme) -> TableBlock:
        thead = next(c for c in node.children if c.type == "thead")
        tbody = next((c for c in node.children if c.type == "tbody"), None)
        headerCells = thead.children[0].children
        headers = [inlineHtmlOf(cell, theme.inlineCode) for cell in headerCells]
        aligns = [_cellAlign(cell) for cell in headerCells]
        rows = (
            [[inlineHtmlOf(cell, theme.inlineCode) for cell in row.children] for row in tbody.children]
            if tbody
            else []
        )
        return TableBlock(headers, rows, aligns)

    def matchAlert(self, node: SyntaxTreeNode) -> str:
        match = _ALERT_RE.match(_leadingText(node).strip())
        return match.group(1).lower() if match else ""

    def matchTask(self, node: SyntaxTreeNode) -> bool | None:
        match = _TASK_RE.match(_leadingText(node))
        if not match:
            return None
        return match.group(1) in "xX"

    def _soleImage(self, node: SyntaxTreeNode) -> SyntaxTreeNode | None:
        if not node.children:
            return None
        inline = node.children[0]
        if len(inline.children) == 1 and inline.children[0].type == "image":
            return inline.children[0]
        return None

    def _markerLabel(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("list-marker")
        label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        return label

    def _taskBox(self, checked: bool) -> QCheckBox:
        box = QCheckBox()
        box.setChecked(checked)
        box.setEnabled(False)  # read-only display in v1
        return box

    def _buildRule(self) -> QFrame:
        rule = QFrame()
        rule.setObjectName("hr")
        rule.setFixedHeight(1)
        return rule


markdownRenderer = MarkdownRenderer()
