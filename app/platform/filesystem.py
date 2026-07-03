import re
import shutil
import sys
from pathlib import Path

INVALID_FILENAME_PATTERN = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]+')
WINDOWS_RESERVED_FILENAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def toSafeFilename(name: str, fallback: str = "file", maxLength: int = 200) -> str:
    candidate = str(name or "")
    lastSep = max(candidate.rfind("/"), candidate.rfind("\\"))
    if lastSep >= 0:
        candidate = candidate[lastSep + 1:]

    candidate = INVALID_FILENAME_PATTERN.sub("_", candidate).strip().rstrip(". ")

    if not candidate or candidate in {".", ".."}:
        return fallback

    root, _, _ = candidate.partition(".")
    if root.upper() in WINDOWS_RESERVED_FILENAMES:
        candidate = f"_{candidate}"

    if 0 < maxLength < len(candidate):
        stem, dot, suffix = candidate.rpartition(".")
        if stem and dot:
            keep = maxLength - len(dot + suffix)
            candidate = f"{stem[:max(1, keep)]}{dot}{suffix}" if keep > 0 else candidate[:maxLength]
        else:
            candidate = candidate[:maxLength]

    return candidate


def deduplicateName(folder: Path, name: str) -> str:
    folder = Path(folder)

    def taken(candidate: str) -> bool:
        target = folder / candidate
        return target.exists() or (folder / f"{candidate}.ghd").exists()

    if not taken(name):
        return name

    suffixes = "".join(Path(name).suffixes)
    stem = name[: -len(suffixes)] if suffixes else name
    index = 1
    while taken(f"{stem}({index}){suffixes}"):
        index += 1
    return f"{stem}({index}){suffixes}"


def toPosixPath(path) -> str:
    return str(Path(path)).replace("\\", "/")


def localFilePath(url: str, validSuffixes: set[str] | None = None) -> Path | None:
    from urllib.parse import urlparse
    from urllib.request import url2pathname
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None

    rawPath = parsed.path
    if parsed.netloc:
        host = parsed.netloc.lower()
        if host == "localhost":
            rawPath = parsed.path
        elif sys.platform == "win32":
            if re.fullmatch(r"[a-zA-Z]:", parsed.netloc):
                rawPath = f"{parsed.netloc}{parsed.path}"
            else:
                rawPath = f"//{parsed.netloc}{parsed.path}"
        else:
            return None

    path = Path(url2pathname(rawPath))
    if not path.is_file():
        return None
    if validSuffixes is not None and path.suffix.lower() not in validSuffixes:
        return None
    return path


def findExecutable(installFolder: Path, name: str, *subdirs: str) -> str:
    exe = f"{name}.exe" if sys.platform == "win32" else name
    for sub in subdirs:
        candidate = installFolder / sub / exe
        if candidate.is_file():
            return toPosixPath(candidate)
    candidate = installFolder / exe
    if candidate.is_file():
        return toPosixPath(candidate)
    found = shutil.which(name)
    return toPosixPath(found) if found else ""


def deletePath(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
