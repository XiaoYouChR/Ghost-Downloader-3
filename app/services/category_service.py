from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from PySide6.QtCore import QObject, Signal
from qfluentwidgets import FluentIcon

from app.supports.config import cfg

if TYPE_CHECKING:
    from app.bases.models import Task


UNCATEGORIZED_ID = ""
DEFAULT_FOLDER_MACRO = "{default}"


def _resolveFolder(folder: str | None) -> str | None:
    if not folder:
        return None
    return folder.replace(DEFAULT_FOLDER_MACRO, cfg.downloadFolder.value)


_DEFAULT_CATEGORY_PRESETS: list[dict[str, Any]] = [
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
        "categoryId": "cat_document",
        "name": "文档",
        "icon": "DOCUMENT",
        "folder": "{default}/Documents",
        "extensions": [
            "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
            "txt", "epub", "mobi", "azw3", "rtf", "odt", "ods",
            "odp", "md", "tif", "tiff",
        ],
    },
    {
        "categoryId": "cat_archive",
        "name": "压缩包",
        "icon": "ZIP_FOLDER",
        "folder": "{default}/Archives",
        "extensions": [
            "zip", "rar", "7z", "tar", "gz", "gzip", "bz2",
            "xz", "tgz", "tbz2", "ace", "arj", "cab", "lzh",
            "sea", "sit", "sitx", "z",
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
            "esd", "wim", "bin",
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

    def fluentIcon(self) -> FluentIcon:
        try:
            return FluentIcon[self.icon]
        except KeyError:
            return FluentIcon.DOCUMENT


def _toCategory(data: dict[str, Any]) -> Category:
    extensions: list[str] = []
    for ext in data.get("extensions") or []:
        normalized = str(ext).strip().lstrip(".").lower()
        if normalized and normalized not in extensions:
            extensions.append(normalized)

    folder = data.get("folder") or None

    return Category(
        categoryId=data.get("categoryId") or f"cat_{uuid4().hex}",
        name=data.get("name") or "",
        icon=data.get("icon") or "DOCUMENT",
        extensions=extensions,
        folder=folder,
    )


class CategoryService(QObject):
    categoriesChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._categories: list[Category] = []
        self._loadFromConfig()

    def _loadFromConfig(self) -> None:
        raw = cfg.categoryRules.value
        if not raw:
            self._categories = [_toCategory(data) for data in _DEFAULT_CATEGORY_PRESETS]
            self._persist()
            return
        self._categories = [_toCategory(data) for data in raw]

    def _persist(self) -> None:
        cfg.set(cfg.categoryRules, [asdict(c) for c in self._categories])

    def categories(self) -> list[Category]:
        return list(self._categories)

    def categoryById(self, categoryId: str) -> Category | None:
        for category in self._categories:
            if category.categoryId == categoryId:
                return category
        return None

    def matchByName(self, filename: str) -> str:
        suffix = Path(filename).suffix.lstrip(".").lower()
        if not suffix:
            return UNCATEGORIZED_ID
        for category in self._categories:
            if suffix in category.extensions:
                return category.categoryId
        return UNCATEGORIZED_ID

    def categoryOf(self, task: "Task") -> str:
        if task.files is not None and len(task.files) > 1:
            return UNCATEGORIZED_ID
        return self.matchByName(task.title)

    def folderOf(self, categoryId: str) -> str | None:
        category = self.categoryById(categoryId)
        if category is None:
            return None
        return _resolveFolder(category.folder)

    def addCategory(self, category: Category) -> None:
        self._categories.append(category)
        self._persist()
        self.categoriesChanged.emit()

    def updateCategory(self, category: Category) -> None:
        for i, existing in enumerate(self._categories):
            if existing.categoryId == category.categoryId:
                self._categories[i] = category
                self._persist()
                self.categoriesChanged.emit()
                return

    def removeCategory(self, categoryId: str) -> None:
        before = len(self._categories)
        self._categories = [c for c in self._categories if c.categoryId != categoryId]
        if len(self._categories) != before:
            self._persist()
            self.categoriesChanged.emit()

    def resetToDefaults(self) -> None:
        self._categories = [_toCategory(data) for data in _DEFAULT_CATEGORY_PRESETS]
        self._persist()
        self.categoriesChanged.emit()

    def reorder(self, categoryIds: list[str]) -> None:
        byId = {c.categoryId: c for c in self._categories}
        reordered = [byId[cid] for cid in categoryIds if cid in byId]
        if len(reordered) != len(self._categories):
            return
        self._categories = reordered
        self._persist()
        self.categoriesChanged.emit()


categoryService = CategoryService()
