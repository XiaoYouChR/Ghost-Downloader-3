# -*- coding: utf-8 -*-
import sys

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
    QWidget,
)
from qfluentwidgets import FluentIcon as FIF, PlainTextEdit
from qfluentwidgets import PushButton, SubtitleLabel, TableWidget, RoundMenu, Action
from qfluentwidgets.components.widgets.button import PrimarySplitPushButton

if sys.platform != "darwin":
    from qfluentwidgets import SmoothScrollArea as ScrollArea
else:
    from qfluentwidgets import ScrollArea


class Ui_AddTaskOptionDialog(object):
    def setupUi(self, AddTaskOptionDialog):
        if not AddTaskOptionDialog.objectName():
            AddTaskOptionDialog.setObjectName("AddTaskOptionDialog")
        self.scrollWidget = QWidget()
        self.scrollWidget.setMinimumSize(QSize(510, 510))
        self.scrollWidget.setStyleSheet("background: transparent")
        self.verticalLayout = QVBoxLayout(self.scrollWidget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.scrollWidget.setLayout(self.verticalLayout)
        self.label = SubtitleLabel(self.scrollWidget)
        self.label.setObjectName("label")

        self.verticalLayout.addWidget(self.label)

        self.linkTextEdit = PlainTextEdit(self.scrollWidget)
        self.linkTextEdit.setObjectName("linkTextEdit")
        self.linkTextEdit.setLineWrapMode(
            PlainTextEdit.LineWrapMode.NoWrap
        )  # 禁用自动换行

        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.linkTextEdit.sizePolicy().hasHeightForWidth())
        self.linkTextEdit.setSizePolicy(sizePolicy)

        self.verticalLayout.addWidget(self.linkTextEdit)

        self.taskTableWidget = TableWidget(self.scrollWidget)
        if self.taskTableWidget.columnCount() < 2:
            self.taskTableWidget.setColumnCount(2)
        __qtablewidgetitem = QTableWidgetItem()
        self.taskTableWidget.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.taskTableWidget.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        self.taskTableWidget.setObjectName("taskTableWidget")
        self.taskTableWidget.verticalHeader().setVisible(False)  # 隐藏垂直表头
        self.taskTableWidget.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )  # 第一列拉伸

        self.verticalLayout.addWidget(self.taskTableWidget)

        # self.statisticLabel = BodyLabel(AddTaskOptionDialog)
        # self.statisticLabel.setObjectName(u"statisticLabel")
        #
        # self.verticalLayout.addWidget(self.statisticLabel)

        self.label_2 = SubtitleLabel(self.scrollWidget)
        self.label_2.setObjectName("label_2")

        self.verticalLayout.addWidget(self.label_2)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setObjectName("buttonLayout")
        self.noButton = PushButton(self.scrollWidget)
        self.noButton.setObjectName("noButton")

        self.buttonLayout.addWidget(self.noButton, stretch=1)

        self.laterMenu = RoundMenu(parent=self.scrollWidget)
        self.laterMenu.setObjectName("laterMenu")
        self.laterAction = Action(FIF.STOP_WATCH, self.tr("稍后下载"))
        self.laterMenu.addAction(self.laterAction)

        self.yesButton = PrimarySplitPushButton(self.scrollWidget)
        self.yesButton.setObjectName("yesButton")

        # Fix PyQt-Fluent-Widgets Bug
        self.yesButton.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _ = self.yesButton.hBoxLayout.takeAt(0).widget()
        _.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.yesButton.hBoxLayout.insertWidget(0, _)

        self.yesButton.setEnabled(False)
        self.yesButton.setFlyout(self.laterMenu)

        self.buttonLayout.addWidget(self.yesButton, stretch=1)

        self.verticalLayout.addLayout(self.buttonLayout)

        self.retranslateUi()

    # setupUi

    def retranslateUi(self):
        self.label.setText(self.tr("新建任务"))
        self.linkTextEdit.setPlaceholderText(
            self.tr("添加多个下载链接时，请确保每行只有一个下载链接")
        )
        ___qtablewidgetitem = self.taskTableWidget.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(self.tr("文件名"))
        ___qtablewidgetitem1 = self.taskTableWidget.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(self.tr("大小"))
        # self.statisticLabel.setText(self.tr("共 0 个文件"))
        self.label_2.setText(self.tr("下载设置"))
        self.noButton.setText(self.tr("取消下载"))
        self.yesButton.setText(self.tr("开始下载"))

    # retranslateUi
