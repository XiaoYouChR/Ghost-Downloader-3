from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.config.constants import RECENT_FOLDER_LIMIT


def loadRecentFolders(folders: tuple[str, ...]) -> tuple[Path, ...]:
    """Check the bounded history on a worker thread, including removable storage."""
    available: list[Path] = []
    for value in folders[:RECENT_FOLDER_LIMIT]:
        if not value or "\x00" in value:
            continue
        folder = Path(value)
        if not folder.is_absolute() or folder in available:
            continue
        try:
            if folder.is_dir():
                available.append(folder)
        except OSError:
            continue
    return tuple(available)


def toWords(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(re.findall(r"[^\W_]+", normalized))


def urlWords(url: str) -> list[tuple[str, ...]]:
    if len(url) > 8192:
        return []
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https", "ftp", "ftps"} or not parsed.hostname:
            return []
        parsed.port  # Invalid ports must not become matching input.
        if re.search(r"%(?![0-9a-fA-F]{2})", parsed.path):
            return []
        path = unquote(parsed.path, errors="strict")
    except (ValueError, UnicodeError):
        return []
    components = path.replace("\\", "/").split("/")
    if any(part in {".", ".."} for part in components):
        return []
    if components and not path.endswith("/"):
        components[-1] = Path(components[-1]).stem
    return [toWords(part) for part in components if part]


def matchFolder(name: str, url: str, folders: tuple[Path, ...]) -> Path | None:
    """Match whole word sequences; equal-strength destinations are ambiguous."""
    if len(name) > 4096:
        return None
    sources = [(2, toWords(Path(name).stem)), *((1, words) for words in urlWords(url))]
    bestScore = (0, 0, 0)
    matches: set[Path] = set()
    for folder in folders[:RECENT_FOLDER_LIMIT]:
        words = toWords(folder.name)
        length = sum(map(len, words))
        if not words or length < 2 or (length < 3 and folder.name.isascii()):
            continue
        for priority, source in sources:
            if not any(source[i:i + len(words)] == words for i in range(len(source) - len(words) + 1)):
                continue
            score = (priority, length, len(words))
            if score > bestScore:
                bestScore, matches = score, {folder}
            elif score == bestScore:
                matches.add(folder)
    return next(iter(matches)) if len(matches) == 1 else None
