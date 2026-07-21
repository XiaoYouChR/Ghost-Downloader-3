from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from app.config.cfg import cfg

if TYPE_CHECKING:
    from app.models.task import Task


DEFAULT_CATEGORY_PRESETS: list[dict[str, Any]] = [
    {
        "categoryId": "cat_video",
        "name": "视频",
        "icon": "VIDEO",
        "folder": "{default}/Video",
        "extensions": [
            "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm",
            "m4v", "rmvb", "rm", "mpg", "mpeg", "mpe", "mpa",
            "3gp", "ts", "m2ts", "ogv", "asf", "qt",
        ],
    },
    {
        "categoryId": "cat_audio",
        "name": "音频",
        "icon": "MUSIC",
        "folder": "{default}/Audio",
        "extensions": [
            "mp3", "flac", "wav", "aac", "ogg", "m4a", "wma",
            "ape", "opus", "mid", "ra", "aif",
        ],
    },
    {
        "categoryId": "cat_image",
        "name": "图片",
        "icon": "PHOTO",
        "folder": "{default}/Images",
        "extensions": [
            "jpg", "jpeg", "png", "gif", "bmp", "webp", "avif",
            "svg", "tif", "tiff", "ico", "heic", "heif",
        ],
    },
    {
        "categoryId": "cat_subtitle",
        "name": "字幕",
        "icon": "CHAT",
        "folder": "{default}/Subtitles",
        "extensions": [
            "srt", "ass", "ssa", "sub", "sup", "idx", "vtt",
            "lrc", "smi", "psb",
        ],
    },
    {
        "categoryId": "cat_document",
        "name": "文档",
        "icon": "DOCUMENT",
        "folder": "{default}/Documents",
        "extensions": [
            "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
            "txt", "epub", "mobi", "azw3", "rtf", "odt", "ods",
            "odp", "md", "csv", "nfo", "chm",
        ],
    },
    {
        "categoryId": "cat_archive",
        "name": "压缩包",
        "icon": "ZIP_FOLDER",
        "folder": "{default}/Archives",
        "extensions": [
            "zip", "rar", "7z", "tar", "gz", "gzip", "bz2",
            "xz", "tgz", "tbz2", "zst", "ace", "arj", "cab", "lzh",
            "sea", "sit", "sitx", "z", "001",
            "tar.gz", "tar.bz2", "tar.xz", "tar.zst",
        ],
    },
    {
        "categoryId": "cat_program",
        "name": "程序",
        "icon": "APPLICATION",
        "folder": "{default}/Programs",
        "extensions": [
            "exe", "msi", "msu", "msp", "apk", "apks", "apkm",
            "dmg", "pkg", "deb", "rpm", "appimage", "iso", "img",
            "esd", "wim", "bin", "jar", "bat", "sh", "com",
        ],
    },
    {
        "categoryId": "cat_other",
        "name": "其他",
        "icon": "HELP",
        "extensions": [],
    },
]


@dataclass(kw_only=True)
class Category:
    categoryId: str = field(default_factory=lambda: f"cat_{uuid4().hex}")
    name: str
    icon: str = "DOCUMENT"
    extensions: list[str] = field(default_factory=list)
    folder: str | None = None

    def toIcon(self):
        from qfluentwidgets import FluentIcon
        return getattr(FluentIcon, self.icon, FluentIcon.TAG)

    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> Category:
        extensions: list[str] = []
        for ext in data.get("extensions") or []:
            normalized = str(ext).strip().lstrip(".").lower()
            if normalized and normalized not in extensions:
                extensions.append(normalized)

        return cls(
            categoryId=data.get("categoryId") or f"cat_{uuid4().hex}",
            name=data.get("name") or "",
            icon=data.get("icon") or "DOCUMENT",
            extensions=extensions,
            folder=data.get("folder") or None,
        )


class CategoryService(QObject):
    categoriesChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._categories: list[Category] = []
        self._load()

    def _load(self) -> None:
        raw = cfg.categoryRules.value
        if not raw:
            self._categories = [Category.fromDict(data) for data in DEFAULT_CATEGORY_PRESETS]
            self._save()
            return
        self._categories = [Category.fromDict(data) for data in raw]

    def _save(self) -> None:
        cfg.set(cfg.categoryRules, [asdict(c) for c in self._categories])
        self.categoriesChanged.emit()

    def categories(self) -> list[Category]:
        return list(self._categories)

    def categoryById(self, categoryId: str) -> Category | None:
        for category in self._categories:
            if category.categoryId == categoryId:
                return category
        return None

    def matchByName(self, filename: str) -> str:
        suffixes = [s.lstrip(".").lower() for s in Path(filename).suffixes]
        if not suffixes:
            return ""

        candidates: list[str] = []
        if len(suffixes) >= 2:
            candidates.append(".".join(suffixes[-2:]))
        candidates.append(suffixes[-1])

        for candidate in candidates:
            for category in self._categories:
                if candidate in category.extensions:
                    return category.categoryId
        return ""

    def categoryOf(self, task: Task) -> str:
        if task.files is not None and len(task.files) > 1:
            return ""
        return self.matchByName(task.name)

    def folderOf(self, categoryId: str) -> str | None:
        category = self.categoryById(categoryId)
        if category is None or not category.folder:
            return None
        return category.folder.replace("{default}", cfg.downloadFolder.value)

    def addCategory(self, category: Category) -> None:
        self._categories.append(category)
        self._save()

    def updateCategory(self, category: Category) -> None:
        for i, existing in enumerate(self._categories):
            if existing.categoryId == category.categoryId:
                self._categories[i] = category
                self._save()
                return

    def removeCategory(self, categoryId: str) -> None:
        before = len(self._categories)
        self._categories = [c for c in self._categories if c.categoryId != categoryId]
        if len(self._categories) != before:
            self._save()

    def reset(self) -> None:
        self._categories = [Category.fromDict(data) for data in DEFAULT_CATEGORY_PRESETS]
        self._save()

    def reorder(self, categoryIds: list[str]) -> None:
        byId = {c.categoryId: c for c in self._categories}
        reordered = [byId[cid] for cid in categoryIds if cid in byId]
        if len(reordered) != len(self._categories):
            return
        self._categories = reordered
        self._save()

