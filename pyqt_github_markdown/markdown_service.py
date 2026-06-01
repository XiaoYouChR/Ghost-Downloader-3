from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode


class MarkdownService:
    def __init__(self):
        # html=False: raw HTML is rendered as escaped text, never interpreted (v1 safety boundary).
        self._md = MarkdownIt("commonmark", {"html": False, "linkify": True})
        self._md.enable(["table", "strikethrough", "linkify"])

    def toTree(self, text: str) -> SyntaxTreeNode:
        return SyntaxTreeNode(self._md.parse(text))


markdownService = MarkdownService()
