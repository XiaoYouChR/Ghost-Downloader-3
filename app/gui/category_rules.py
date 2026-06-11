from collections.abc import Callable
from uuid import uuid4

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Slot

# 设置页「管理分类」的规则列表（增删自定义分类规则）。改动经注入的 onChanged 落盘 + 同步引擎。
# 沿用 UserAgentModel 的通用列表编辑器范式，字段更多：名字 / 图标语义名 / 目录 / 扩展名集。
_ICON_CHOICES = ["VIDEO", "MUSIC", "PHOTO", "CHAT", "DOCUMENT", "ZIP_FOLDER", "APPLICATION", "HELP"]


class CategoryRuleModel(QAbstractListModel):
    NameRole = Qt.ItemDataRole.UserRole + 1
    IconRole = Qt.ItemDataRole.UserRole + 2
    FolderRole = Qt.ItemDataRole.UserRole + 3
    ExtensionsRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, rules: list, onChanged: Callable[[list], None] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._rules = [dict(rule) for rule in rules]
        self._onChanged = onChanged

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rules)

    def data(self, index, role):
        if not index.isValid():
            return None
        rule = self._rules[index.row()]
        if role == self.NameRole:
            return rule.get("name", "")
        if role == self.IconRole:
            return rule.get("icon", "DOCUMENT")
        if role == self.FolderRole:
            return rule.get("folder", "")
        if role == self.ExtensionsRole:
            return ", ".join(rule.get("extensions", []))
        return None

    def roleNames(self):
        return {
            self.NameRole: b"name", self.IconRole: b"icon",
            self.FolderRole: b"folder", self.ExtensionsRole: b"extensionsText",
        }

    @Slot(str, str, str, str)
    def add(self, name: str, extensionsText: str, folder: str, icon: str) -> None:
        extensions = [e.strip().lstrip(".").lower() for e in extensionsText.replace("，", ",").split(",")]
        extensions = [e for e in extensions if e]
        if not name.strip() or not extensions:
            return  # 名字空或没填扩展名就不收
        row = len(self._rules)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rules.append({
            "categoryId": f"cat_{uuid4().hex}", "name": name.strip(),
            "icon": icon if icon in _ICON_CHOICES else "DOCUMENT",
            "folder": folder.strip(), "extensions": extensions,
        })
        self.endInsertRows()
        self._persist()

    @Slot(int)
    def removeAt(self, row: int) -> None:
        if not 0 <= row < len(self._rules):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._rules[row]
        self.endRemoveRows()
        self._persist()

    def _persist(self) -> None:
        if self._onChanged is not None:
            self._onChanged([dict(rule) for rule in self._rules])
