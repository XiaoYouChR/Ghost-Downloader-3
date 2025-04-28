# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'Ui_AddTaskOptionDialog.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QSize)
from PySide6.QtWidgets import (QHBoxLayout, QSizePolicy, QTableWidgetItem, QVBoxLayout, QHeaderView)
from qfluentwidgets import FluentIcon as FIF, PlainTextEdit
from qfluentwidgets import (PushButton, SubtitleLabel,
                            TableWidget, RoundMenu, Action)
from qfluentwidgets.components.widgets.button import PrimarySplitPushButton


class Ui_AddTaskOptionDialog(object):
    def setupUi(self, AddTaskOptionDialog):
        if not AddTaskOptionDialog.objectName():
            AddTaskOptionDialog.setObjectName(u"AddTaskOptionDialog")
        AddTaskOptionDialog.resize(680, 800)
        AddTaskOptionDialog.setMinimumSize(QSize(510, 620))
        AddTaskOptionDialog.setMaximumSize(QSize(680, 680))
        self.verticalLayout = QVBoxLayout(AddTaskOptionDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.label = SubtitleLabel(AddTaskOptionDialog)
        self.label.setObjectName(u"label")

        self.verticalLayout.addWidget(self.label)

        self.linkTextEdit = PlainTextEdit(AddTaskOptionDialog)
        self.linkTextEdit.setObjectName(u"linkTextEdit")
        self.linkTextEdit.setLineWrapMode(PlainTextEdit.LineWrapMode.NoWrap)  # 禁用自动换行

        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.linkTextEdit.sizePolicy().hasHeightForWidth())
        self.linkTextEdit.setSizePolicy(sizePolicy)

        self.verticalLayout.addWidget(self.linkTextEdit)

        self.taskTableWidget = TableWidget(AddTaskOptionDialog)
        if (self.taskTableWidget.columnCount() < 2):
            self.taskTableWidget.setColumnCount(2)
        __qtablewidgetitem = QTableWidgetItem()
        self.taskTableWidget.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.taskTableWidget.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        self.taskTableWidget.setObjectName(u"taskTableWidget")
        self.taskTableWidget.verticalHeader().setVisible(False)  # 隐藏垂直表头
        self.taskTableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)  # 第一列拉伸

        self.verticalLayout.addWidget(self.taskTableWidget)

        # self.statisticLabel = BodyLabel(AddTaskOptionDialog)
        # self.statisticLabel.setObjectName(u"statisticLabel")
        #
        # self.verticalLayout.addWidget(self.statisticLabel)

        self.label_2 = SubtitleLabel(AddTaskOptionDialog)
        self.label_2.setObjectName(u"label_2")

        self.verticalLayout.addWidget(self.label_2)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setObjectName(u"buttonLayout")
        self.noButton = PushButton(AddTaskOptionDialog)
        self.noButton.setObjectName(u"noButton")

        self.buttonLayout.addWidget(self.noButton, stretch=1)

        self.laterMenu = RoundMenu(parent=AddTaskOptionDialog)
        self.laterMenu.setObjectName(u"laterMenu")
        self.laterAction = Action(FIF.STOP_WATCH, "稍后下载")
        self.laterMenu.addAction(self.laterAction)

        self.yesButton = PrimarySplitPushButton(AddTaskOptionDialog)
        self.yesButton.setObjectName(u"yesButton")

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
        self.label.setText(QCoreApplication.translate("AddTaskOptionDialog", u"新建任务", None))
        self.linkTextEdit.setPlaceholderText(QCoreApplication.translate("AddTaskOptionDialog", u"添加多个下载链接时，请确保每行只有一个下载链接", None))
        ___qtablewidgetitem = self.taskTableWidget.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("AddTaskOptionDialog", u"文件名", None));
        ___qtablewidgetitem1 = self.taskTableWidget.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("AddTaskOptionDialog", u"大小", None));
        # self.statisticLabel.setText(QCoreApplication.translate("AddTaskOptionDialog", u"共 0 个文件", None))
        self.label_2.setText(QCoreApplication.translate("AddTaskOptionDialog", u"下载设置", None))
        self.noButton.setText(QCoreApplication.translate("AddTaskOptionDialog", u"取消下载", None))
        self.yesButton.setText(QCoreApplication.translate("AddTaskOptionDialog", u"开始下载", None))
    # retranslateUi

