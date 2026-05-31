import html

import emoji
from markdown_it.tree import SyntaxTreeNode


def inlineHtmlOf(blockNode: SyntaxTreeNode, inlineCode: str) -> str:
    # A block (paragraph, heading, table cell) wraps its inline content in a single "inline" child.
    if not blockNode.children:
        return ""
    return toInlineHtml(blockNode.children[0], inlineCode)


def toInlineHtml(inlineNode: SyntaxTreeNode, inlineCode: str) -> str:
    return "".join(_token(child, inlineCode) for child in inlineNode.children)


def _token(node: SyntaxTreeNode, inlineCode: str) -> str:
    match node.type:
        case "text":
            return html.escape(emoji.emojize(node.content, language="alias"))
        case "softbreak":
            return " "
        case "hardbreak":
            return "<br>"
        case "code_inline":
            # Qt rich text supports background-color/font on an inline span but not padding
            # or rounding, so this is a flat tinted span rather than GitHub's rounded pill.
            return f'<code style="{inlineCode}">{html.escape(node.content)}</code>'
        case "strong":
            return f"<b>{_children(node, inlineCode)}</b>"
        case "em":
            return f"<i>{_children(node, inlineCode)}</i>"
        case "s":
            return f"<s>{_children(node, inlineCode)}</s>"
        case "link":
            href = html.escape(node.attrs.get("href", ""), quote=True)
            return f'<a href="{href}">{_children(node, inlineCode)}</a>'
        case "image":
            # Inline images among text fall back to their alt text; image-only paragraphs
            # are caught upstream and become an ImagePlaceholder instead.
            alt = html.escape(node.content or "")
            return f"[{alt}]" if alt else ""
        case "html_inline":
            return html.escape(node.content)
        case _:
            return _children(node, inlineCode)


def _children(node: SyntaxTreeNode, inlineCode: str) -> str:
    return "".join(_token(child, inlineCode) for child in node.children)
