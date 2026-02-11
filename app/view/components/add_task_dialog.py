from typing import Any

from PySide6.QtCore import QEvent, Qt, QPoint, QObject, QMargins, QFileInfo
from PySide6.QtGui import QTextOption, QMouseEvent, QColor, QPainter
from PySide6.QtWidgets import QTextEdit, QWidget, QVBoxLayout, QLayout, QSizePolicy, QHBoxLayout, QSpacerItem, \
    QFileIconProvider
from qfluentwidgets import MessageBoxBase, SubtitleLabel, TextEdit, ScrollArea, SettingCardGroup, SimpleCardWidget, \
    ImageLabel, LineEdit, Action, FluentIcon, GroupHeaderCardWidget, BodyLabel, StrongBodyLabel, isDarkTheme

from app.supports.config import cfg
from app.supports.utils import getReadableSize
from app.view.components.setting_cards import SelectFolderSettingCard


class ResultCardBase(QWidget):
    """显示下载链接解析结果的卡片组件"""
    
    def __init__(self, filename: str, fileSize: int, url: str, parent: QWidget = None):
        super().__init__(parent)
        self.filename = filename
        self.fileSize = fileSize
        self.url = url
        self.borderRadius = 5

        self.iconLabel = ImageLabel(self)
        self.filenameLabel = StrongBodyLabel(filename, self)
        self.filenameEdit = LineEdit(self)
        self.sizeLabel = BodyLabel(getReadableSize(fileSize), self)
        self.mainLayout = QHBoxLayout(self)

        self.initWidget()
        self.initLayout()
        
    def initWidget(self):
        """初始化组件属性"""
        self.setFixedHeight(35)
        self.resetFileIcon()
        # 设置文件名标签
        self.filenameLabel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filenameLabel.installEventFilter(self)
        # 设置编辑框
        self.filenameEdit.setText(self.filename)
        self.filenameEdit.editingFinished.connect(self._onEditingFinished)
        self.filenameEdit.hide()
        
    def initLayout(self):
        """初始化布局"""
        self.mainLayout.setContentsMargins(10, 2, 10, 2)
        self.mainLayout.setSpacing(12)
        self.mainLayout.addWidget(self.iconLabel)
        self.mainLayout.addWidget(self.filenameLabel)
        self.mainLayout.addWidget(self.filenameEdit)
        self.mainLayout.addStretch()
        self.mainLayout.addWidget(self.sizeLabel)
        
    def eventFilter(self, obj, event: QEvent):
        """事件过滤器，处理双击事件"""
        if obj is self.filenameLabel:
            if event.type() == QEvent.Type.MouseButtonDblClick and isinstance(event, QMouseEvent):
                if event.button() == Qt.MouseButton.LeftButton:
                    self._enterEditMode()
                    return True
        return super().eventFilter(obj, event)

    def resetFileIcon(self):
        icon = QFileIconProvider().icon(QFileInfo(self.filename))
        self.iconLabel.setImage(icon.pixmap(16, 16))
        self.iconLabel.setFixedSize(16, 16)

    def _enterEditMode(self):
        """进入编辑模式"""
        self.filenameLabel.hide()
        self.filenameEdit.show()
        self.filenameEdit.setFocus()
        self.filenameEdit.selectAll()
        
    def _onEditingFinished(self):
        """编辑完成回调"""
        newFilename = self.filenameEdit.text().strip()
        if newFilename and newFilename != self.filename:
            self.filename = newFilename
            self.filenameLabel.setText(newFilename)
            self.resetFileIcon()

        self.filenameEdit.hide()
        self.filenameLabel.show()
        self.filenameLabel.setFocus()
        
    def getData(self) -> dict:
        """获取卡片数据"""
        return {
            "filename": self.filename,
            "file_size": self.file_size,
            "url": self.url
        }

    def setFilename(self, filename: str):
        """设置文件名"""
        self.filename = filename
        self.filenameLabel.setText(filename)
        self.filenameEdit.setText(filename)

    @property
    def backgroundColor(self):
        return QColor(255, 255, 255, 13 if isDarkTheme() else 200)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.backgroundColor)

        if isDarkTheme():
            painter.setPen(QColor(255, 255, 255, 46))
        else:
            painter.setPen(QColor(0, 0, 0, 12))

        r = self.borderRadius
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), r, r)


class AddTaskDialog(MessageBoxBase):

    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("添加任务"), self)
        self.urlEdit = TextEdit(self)
        self.scrollArea = ScrollArea(self)
        self.scrollWidget = QWidget(self)
        self.scrollLayout = QVBoxLayout(self.scrollWidget)
        self.settingGroup = GroupHeaderCardWidget(self)
        self.pathEdit = LineEdit(self)
        self.selectFolderAction = Action(FluentIcon.FOLDER, self.tr("选择文件夹"), self)

        self.initWidget()
        self.initLayout()
        # TODO For Test
        # self.scrollArea.hide()
        for i in range(5):
            self.scrollLayout.addWidget(ResultCardBase(f"ssis-448-{i}.avi", 123456789, "https://example.com/ssis-448.avi", self.scrollWidget))


    def initWidget(self):
        self.setObjectName("AddTaskDialog")
        self.widget.setFixedWidth(700)

        self.urlEdit.setPlaceholderText(self.tr("添加多个下载链接时，请确保每行只有一个下载链接"))
        self.urlEdit.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        # Setting Group
        self.settingGroup.setTitle(self.tr("下载设置"))
        self.pathEdit.addAction(self.selectFolderAction)
        self.settingGroup.addGroup(FluentIcon.DOWNLOAD, self.tr("选择下载路径"), self.tr("下载路径"), self.pathEdit, 2)

        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.enableTransparentBackground()

    def initLayout(self):
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.urlEdit)
        self.viewLayout.addWidget(self.scrollArea)
        self.viewLayout.addWidget(self.settingGroup)

        self.scrollLayout.setContentsMargins(0, 0, 0, 0)
        self.scrollLayout.setSpacing(0)

    def parse(self, payload: dict[str, Any]):
        ...

    def done(self, code):
        ...
        super().done(code)

    def addParseResult(self, filename: str, file_size: int, url: str):
        """添加解析结果卡片到滚动区域"""
        resultCard = ResultCardBase(filename, file_size, url, self.scrollWidget)
        self.scrollLayout.addWidget(resultCard)
        return resultCard
        
    def clearResults(self):
        """清空所有解析结果"""
        while self.scrollLayout.count():
            child = self.scrollLayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
    def getAllResults(self) -> list:
        """获取所有解析结果的数据"""
        results = []
        for i in range(self.scrollLayout.count()):
            widget = self.scrollLayout.itemAt(i).widget()
            if isinstance(widget, ResultCardBase):
                results.append(widget.getData())
        return results

    @classmethod
    def display(cls, payload: dict[str, Any]=None, parent=None):
        if cls._instance is None:
            cls._instance = cls(parent)

        cls._instance.exec()

    def closeEvent(self, e):
        self.urlEdit.clear()
        self.clearResults()
        return super().closeEvent(e)

    def eventFilter(self, obj, e: QEvent):
        if obj is self.windowMask:
            if e.type() == QEvent.Type.MouseButtonPress and e.button() == Qt.MouseButton.LeftButton:
                self._dragPos = e.pos()
                return True
            elif e.type() == QEvent.Type.MouseMove and not self._dragPos.isNull():
                pos = self.window().pos() + e.pos() - self._dragPos
                pos.setX(max(0, pos.x()))
                pos.setY(max(0, pos.y()))

                self.window().move(pos)
                return True
            elif e.type() == QEvent.Type.MouseButtonRelease:
                self._dragPos = QPoint()

        return super().eventFilter(obj, e)
