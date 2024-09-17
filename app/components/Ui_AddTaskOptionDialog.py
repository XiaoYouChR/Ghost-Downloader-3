# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'Ui_AddTaskOptionDialog.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QMetaObject, QSize)
from PySide6.QtWidgets import (QHBoxLayout, QSizePolicy, QTableWidgetItem, QVBoxLayout)

from qfluentwidgets import (PrimaryPushButton, PushButton, SubtitleLabel,
                            TableWidget, TextEdit)

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

        self.linkTextEdit = TextEdit(AddTaskOptionDialog)
        self.linkTextEdit.setObjectName(u"linkTextEdit")
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

        self.buttonLayout.addWidget(self.noButton)

        self.yesButton = PrimaryPushButton(AddTaskOptionDialog)
        self.yesButton.setObjectName(u"yesButton")
        self.yesButton.setEnabled(False)

        self.buttonLayout.addWidget(self.yesButton)


        self.verticalLayout.addLayout(self.buttonLayout)


        self.retranslateUi(AddTaskOptionDialog)

        QMetaObject.connectSlotsByName(AddTaskOptionDialog)
    # setupUi

    def retranslateUi(self, AddTaskOptionDialog):
        self.label.setText(QCoreApplication.translate("AddTaskOptionDialog", u"\u65b0\u5efa\u4efb\u52a1", None))
        self.linkTextEdit.setPlaceholderText(QCoreApplication.translate("AddTaskOptionDialog", u"\u6dfb\u52a0\u591a\u4e2a\u4e0b\u8f7d\u94fe\u63a5\u65f6\uff0c\u8bf7\u786e\u4fdd\u6bcf\u884c\u53ea\u6709\u4e00\u4e2a\u4e0b\u8f7d\u94fe\u63a5", None))
        ___qtablewidgetitem = self.taskTableWidget.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("AddTaskOptionDialog", u"\u6587\u4ef6\u540d", None));
        ___qtablewidgetitem1 = self.taskTableWidget.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("AddTaskOptionDialog", u"\u5927\u5c0f", None));
        # self.statisticLabel.setText(QCoreApplication.translate("AddTaskOptionDialog", u"\u5171 0 \u4e2a\u6587\u4ef6", None))
        self.label_2.setText(QCoreApplication.translate("AddTaskOptionDialog", u"\u4e0b\u8f7d\u8bbe\u7f6e", None))
        self.noButton.setText(QCoreApplication.translate("AddTaskOptionDialog", u"\u53d6\u6d88\u4e0b\u8f7d", None))
        self.yesButton.setText(QCoreApplication.translate("AddTaskOptionDialog", u"\u5f00\u59cb\u4e0b\u8f7d", None))
    # retranslateUi

