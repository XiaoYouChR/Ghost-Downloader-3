# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'Ui_PopUpWindow.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QRect, Qt)
from PySide6.QtWidgets import (QLabel, QToolButton)

from qfluentwidgets import PixmapLabel

class Ui_PopUpWindow(object):
    def setupUi(self, PopUpWindow):
        if not PopUpWindow.objectName():
            PopUpWindow.setObjectName(u"PopUpWindow")
        PopUpWindow.setFixedSize(362, 125)
        self.contentIconLabel = PixmapLabel(PopUpWindow)
        self.contentIconLabel.setObjectName(u"contentIconLabel")
        self.contentIconLabel.setGeometry(QRect(15, 41, 65, 65))
        self.logoLabel = PixmapLabel(PopUpWindow)
        self.logoLabel.setObjectName(u"logoLabel")
        self.logoLabel.setGeometry(QRect(15, 15, 16, 16))
        self.titleLabel = QLabel(PopUpWindow)
        self.titleLabel.setObjectName(u"titleLabel")
        self.titleLabel.setGeometry(QRect(40, 12, 231, 19))
        self.captionLabel = QLabel(PopUpWindow)
        self.captionLabel.setObjectName(u"captionLabel")
        self.captionLabel.setGeometry(QRect(90, 40, 261, 20))
        self.contentLabel = QLabel(PopUpWindow)
        self.contentLabel.setObjectName(u"contentLabel")
        self.contentLabel.setGeometry(QRect(90, 60, 261, 50))
        self.contentLabel.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.contentLabel.setWordWrap(True)
        self.closeBtn = QToolButton(PopUpWindow)
        self.closeBtn.setObjectName(u"closeBtn")
        self.closeBtn.setGeometry(QRect(320, 13, 24, 24))

        self.retranslateUi(PopUpWindow)
    # setupUi

    def retranslateUi(self, PopUpWindow):
        self.titleLabel.setText(QCoreApplication.translate("PopUpWindow", u"Ghost Downloader", None))
    # retranslateUi

