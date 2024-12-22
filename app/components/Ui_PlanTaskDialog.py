# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'PlanTaskDialog.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QRect,
                            QSize)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (LineEdit, PrimaryPushButton, PrimaryToolButton, PushButton,
                            RadioButton, SubtitleLabel)


class Ui_PlanTaskDialog(object):
    def setupUi(self, Form):
        if not Form.objectName():
            Form.setObjectName(u"PlanTaskDialog")
        Form.resize(410, 225)
        Form.setFixedSize(QSize(410, 225))

        self.powerOffButton = RadioButton(Form)
        self.powerOffButton.setObjectName(u"powerOffButton")
        self.powerOffButton.setGeometry(QRect(30, 55, 112, 24))
        self.powerOffButton.setChecked(True)

        self.quitButton = RadioButton(Form)
        self.quitButton.setObjectName(u"quitButton")
        self.quitButton.setGeometry(QRect(230, 55, 112, 24))

        self.openFileButton = RadioButton(Form)
        self.openFileButton.setObjectName(u"openFileButton")
        self.openFileButton.setGeometry(QRect(30, 95, 112, 24))

        self.filePathEdit = LineEdit(Form)
        self.filePathEdit.setObjectName(u"filePathEdit")
        self.filePathEdit.setGeometry(QRect(20, 130, 326, 33))
        self.filePathEdit.setReadOnly(True)
        self.filePathEdit.setEnabled(False)

        self.selectFileButton = PrimaryToolButton(Form)
        self.selectFileButton.setObjectName(u"selectFileButton")
        self.selectFileButton.setGeometry(QRect(350, 130, 33, 33))
        self.selectFileButton.setEnabled(False)
        self.selectFileButton.setIcon(FIF.FOLDER)

        self.yesButton = PrimaryPushButton(Form)
        self.yesButton.setObjectName(u"yesButton")
        self.yesButton.setGeometry(QRect(212, 180, 181, 32))

        self.noButton = PushButton(Form)
        self.noButton.setObjectName(u"noButton")
        self.noButton.setGeometry(QRect(20, 180, 181, 32))

        self.SubtitleLabel = SubtitleLabel(Form)
        self.SubtitleLabel.setObjectName(u"SubtitleLabel")
        self.SubtitleLabel.setGeometry(QRect(20, 10, 131, 38))

        self.retranslateUi(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QCoreApplication.translate("Form", u"Form", None))
        self.powerOffButton.setText(QCoreApplication.translate("Form", u"\u5173\u673a", None))
        self.quitButton.setText(QCoreApplication.translate("Form", u"\u9000\u51fa\u7a0b\u5e8f", None))
        self.openFileButton.setText(QCoreApplication.translate("Form", u"\u6253\u5f00", None))
        self.yesButton.setText(QCoreApplication.translate("Form", u"\u8bbe\u7f6e\u8ba1\u5212\u4efb\u52a1", None))
        self.noButton.setText(QCoreApplication.translate("Form", u"\u53d6\u6d88", None))
        self.SubtitleLabel.setText(QCoreApplication.translate("Form", u"\u8bbe\u7f6e\u8ba1\u5212\u4efb\u52a1", None))
