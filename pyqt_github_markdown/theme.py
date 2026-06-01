from dataclasses import dataclass
from string import Template

# Colours live here as a single source of truth: the QSS, the inline-code background, and the
# alert icon colours all derive from one palette per theme. Builder code never names a colour;
# it reads what it needs off the Theme it is handed. Switching theme = swap qss + codeStyle and
# rebuild (code highlight and icon colours are baked in at build time).

_ALERT_KINDS = ("note", "tip", "important", "warning", "caution")


@dataclass(frozen=True)
class Theme:
    qss: str
    codeStyle: str  # Pygments style name for fenced code blocks
    inlineCode: str  # CSS style value for inline <code> spans
    alertColors: dict[str, str]  # alert kind -> hex, drives both border and icon


_QSS = Template(
    """
#markdown, #markdown QWidget {
    background: $bg;
    color: $text;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 16px;
}
QLabel#h1 { font-size: 30px; font-weight: 600; border-bottom: 1px solid $border; padding-bottom: 6px; }
QLabel#h2 { font-size: 22px; font-weight: 600; border-bottom: 1px solid $border; padding-bottom: 6px; }
QLabel#h3 { font-size: 18px; font-weight: 600; }
QLabel#h4 { font-size: 16px; font-weight: 600; }
QLabel#h5 { font-size: 14px; font-weight: 600; }
QLabel#h6 { font-size: 13px; font-weight: 600; color: $mutedText; }
QLabel#paragraph { font-size: 16px; }
QFrame#hr { background: $border; border: none; }

#blockquote { border-left: 4px solid $border; }
#blockquote QLabel { color: $mutedText; }

#alert { border-left: 4px solid $border; }
#alert[kind="note"]      { border-left-color: $noteColor; }
#alert[kind="tip"]       { border-left-color: $tipColor; }
#alert[kind="important"] { border-left-color: $importantColor; }
#alert[kind="warning"]   { border-left-color: $warningColor; }
#alert[kind="caution"]   { border-left-color: $cautionColor; }
QLabel#alert-title { font-weight: 600; }
#alert[kind="note"]      QLabel#alert-title { color: $noteColor; }
#alert[kind="tip"]       QLabel#alert-title { color: $tipColor; }
#alert[kind="important"] QLabel#alert-title { color: $importantColor; }
#alert[kind="warning"]   QLabel#alert-title { color: $warningColor; }
#alert[kind="caution"]   QLabel#alert-title { color: $cautionColor; }

#code-block { background: $codeBg; border: 1px solid $border; border-radius: 6px; }
QLabel#code-lang { color: $mutedText; font-size: 12px; }
QToolButton#code-copy { color: $mutedText; border: 1px solid $border; border-radius: 4px; padding: 1px 8px; background: $codeBg; }
QToolButton#code-copy:hover { background: $stripe; }
QTextEdit#code-editor { background: $codeBg; border: none; }

QLabel[role="cell"]   { border: 1px solid $border; padding: 6px 13px; }
QLabel[role="header"] { border: 1px solid $border; padding: 6px 13px; font-weight: 600; background: $codeBg; }
QLabel[role="cell"][odd="true"] { background: $codeBg; }

QLabel#list-marker { color: $text; }
"""
)


def _buildTheme(palette: dict[str, str], codeStyle: str) -> Theme:
    inlineCode = (
        f"background-color:{palette['inlineCodeBg']};"
        " font-family:Consolas,'Courier New',monospace;"
    )
    alertColors = {kind: palette[f"{kind}Color"] for kind in _ALERT_KINDS}
    return Theme(
        qss=_QSS.substitute(palette),
        codeStyle=codeStyle,
        inlineCode=inlineCode,
        alertColors=alertColors,
    )


_LIGHT_PALETTE = {
    "text": "#1f2328",
    "bg": "#ffffff",
    "border": "#d0d7de",
    "mutedText": "#59636e",
    "codeBg": "#f6f8fa",
    "stripe": "#eaeef2",
    "inlineCodeBg": "#eaeef2",
    "noteColor": "#0969da",
    "tipColor": "#1a7f37",
    "importantColor": "#8250df",
    "warningColor": "#9a6700",
    "cautionColor": "#cf222e",
}

_DARK_PALETTE = {
    "text": "#e6edf3",
    "bg": "#0d1117",
    "border": "#30363d",
    "mutedText": "#8b949e",
    "codeBg": "#161b22",
    "stripe": "#21262d",
    "inlineCodeBg": "#343941",
    "noteColor": "#2f81f7",
    "tipColor": "#3fb950",
    "importantColor": "#a371f7",
    "warningColor": "#d29922",
    "cautionColor": "#f85149",
}

LIGHT = _buildTheme(_LIGHT_PALETTE, "default")
DARK = _buildTheme(_DARK_PALETTE, "github-dark")
