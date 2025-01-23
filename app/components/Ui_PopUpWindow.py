# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'Ui_PopUpWindow.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QRect)

from qfluentwidgets import (CaptionLabel, PixmapLabel, PrimaryPushButton, PushButton,
    ToolButton)

class Ui_PopUpWindow(object):
    def setupUi(self, PopUpWindow):
        if not PopUpWindow.objectName():
            PopUpWindow.setObjectName(u"PopUpWindow")
        PopUpWindow.resize(270, 90)
        self.pixmapLabel = PixmapLabel(PopUpWindow)
        self.pixmapLabel.setObjectName(u"pixmapLabel")
        self.pixmapLabel.setGeometry(QRect(10, 30, 51, 51))
        self.pixmapLabel.setStyleSheet(u"")
        self.fileNameLabel = CaptionLabel(PopUpWindow)
        self.fileNameLabel.setObjectName(u"fileNameLabel")
        self.fileNameLabel.setGeometry(QRect(70, 40, 191, 20))
        self.openFileBtn = PrimaryPushButton(PopUpWindow)
        self.openFileBtn.setObjectName(u"openFileBtn")
        self.openFileBtn.setGeometry(QRect(70, 62, 91, 20))
        self.openPathBtn = PushButton(PopUpWindow)
        self.openPathBtn.setObjectName(u"openPathBtn")
        self.openPathBtn.setGeometry(QRect(170, 62, 91, 21))
        self.closeBtn = ToolButton(PopUpWindow)
        self.closeBtn.setObjectName(u"closeBtn")
        self.closeBtn.setGeometry(QRect(245, 5, 20, 20))
        self.showMainWindowBtn = ToolButton(PopUpWindow)
        self.showMainWindowBtn.setObjectName(u"showMainWindowBtn")
        self.showMainWindowBtn.setGeometry(QRect(220, 5, 20, 20))
        self.titleLabel = CaptionLabel(PopUpWindow)
        self.titleLabel.setObjectName(u"titleLabel")
        self.titleLabel.setGeometry(QRect(10, 5, 201, 16))
        self.captionLabel = CaptionLabel(PopUpWindow)
        self.captionLabel.setObjectName(u"captionLabel")
        self.captionLabel.setGeometry(QRect(70, 25, 191, 16))

        self.retranslateUi(PopUpWindow)

    # setupUi

    def retranslateUi(self, PopUpWindow):
        PopUpWindow.setWindowTitle(QCoreApplication.translate("PopUpWindow", u"Form", None))
        self.openFileBtn.setText(QCoreApplication.translate("PopUpWindow", u"\u7acb\u5373\u6253\u5f00", None))
        self.openPathBtn.setText(QCoreApplication.translate("PopUpWindow", u"\u6253\u5f00\u76ee\u5f55", None))
        self.titleLabel.setText(QCoreApplication.translate("PopUpWindow", u"Ghost Downloader", None))
        self.captionLabel.setText(QCoreApplication.translate("PopUpWindow", u"\u4e0b\u8f7d\u5b8c\u6210 :", None))
    # retranslateUi
