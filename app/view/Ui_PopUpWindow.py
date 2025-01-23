# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'Ui_PopUpWindow.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QRect)
from PySide6.QtWidgets import (QPushButton, QLabel)

from qfluentwidgets import (BodyLabel, PixmapLabel, PushButton)

class Ui_PopUpWindow(object):
    def setupUi(self, PopUpWindow):
        if not PopUpWindow.objectName():
            PopUpWindow.setObjectName(u"PopUpWindow")
        PopUpWindow.setFixedSize(362, 125)
        self.fileIconLabel = PixmapLabel(PopUpWindow)
        self.fileIconLabel.setObjectName(u"fileIconLabel")
        self.fileIconLabel.setGeometry(QRect(15, 41, 65, 65))
        self.logoLabel = PixmapLabel(PopUpWindow)
        self.logoLabel.setObjectName(u"logoLabel")
        self.logoLabel.setGeometry(QRect(15, 15, 16, 16))
        self.titleLabel = BodyLabel(PopUpWindow)
        self.titleLabel.setObjectName(u"titleLabel")
        self.titleLabel.setGeometry(QRect(40, 12, 231, 19))
        self.openPathBtn = PushButton(PopUpWindow)
        self.openPathBtn.setObjectName(u"openPathBtn")
        self.openPathBtn.setGeometry(QRect(90, 80, 125, 28))
        self.openFileBtn = PushButton(PopUpWindow)
        self.openFileBtn.setObjectName(u"openFileBtn")
        self.openFileBtn.setGeometry(QRect(223, 80, 125, 28))
        self.captionLabel = QLabel(PopUpWindow)
        self.captionLabel.setObjectName(u"captionLabel")
        self.captionLabel.setGeometry(QRect(90, 40, 261, 16))
        self.fileNameLabel = QLabel(PopUpWindow)
        self.fileNameLabel.setObjectName(u"fileNameLabel")
        self.fileNameLabel.setGeometry(QRect(90, 60, 261, 16))
        self.closeBtn = QPushButton(PopUpWindow)
        self.closeBtn.setObjectName(u"closeBtn")
        self.closeBtn.setGeometry(QRect(320, 13, 24, 24))
        self.mainWindowBtn = QPushButton(PopUpWindow)
        self.mainWindowBtn.setObjectName(u"mainWindowBtn")
        self.mainWindowBtn.setGeometry(QRect(280, 13, 24, 24))

        self.retranslateUi(PopUpWindow)
    # setupUi

    def retranslateUi(self, PopUpWindow):
        self.titleLabel.setText(QCoreApplication.translate("PopUpWindow", u"Ghost Downloader", None))
        self.openPathBtn.setText(QCoreApplication.translate("PopUpWindow", u"\u6253\u5f00\u76ee\u5f55", None))
        self.openFileBtn.setText(QCoreApplication.translate("PopUpWindow", u"\u6253\u5f00\u6587\u4ef6", None))
        self.captionLabel.setText(QCoreApplication.translate("PopUpWindow", u"\u4e0b\u8f7d\u5b8c\u6210", None))
    # retranslateUi

