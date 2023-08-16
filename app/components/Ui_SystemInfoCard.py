# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'SystemInfoCard.ui'
##
## Created by: Qt User Interface Compiler version 6.4.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QSizePolicy, QVBoxLayout,
    QWidget)

from qfluentwidgets import (BodyLabel, CardWidget, PixmapLabel, PrimarySplitPushButton,
    SplitPushButton, TitleLabel)

class Ui_SystemInfoCard(object):
    def setupUi(self, SystemInfoCard):
        if not SystemInfoCard.objectName():
            SystemInfoCard.setObjectName(u"SystemInfoCard")
        SystemInfoCard.resize(793, 131)
        SystemInfoCard.setMinimumSize(QSize(793, 131))
        SystemInfoCard.setMaximumSize(QSize(16777215, 131))
        self.horizontalLayout = QHBoxLayout(SystemInfoCard)
        self.horizontalLayout.setSpacing(12)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.LogoPixmapLabel = PixmapLabel(SystemInfoCard)
        self.LogoPixmapLabel.setObjectName(u"LogoPixmapLabel")
        self.LogoPixmapLabel.setMinimumSize(QSize(101, 101))
        self.LogoPixmapLabel.setMaximumSize(QSize(101, 101))
        self.LogoPixmapLabel.setScaledContents(True)
        self.LogoPixmapLabel.setAlignment(Qt.AlignCenter)

        self.horizontalLayout.addWidget(self.LogoPixmapLabel)

        self.BodyVBoxLayout = QVBoxLayout()
        self.BodyVBoxLayout.setSpacing(0)
        self.BodyVBoxLayout.setObjectName(u"BodyVBoxLayout")
        self.TitleLabel = TitleLabel(SystemInfoCard)
        self.TitleLabel.setObjectName(u"TitleLabel")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.TitleLabel.sizePolicy().hasHeightForWidth())
        self.TitleLabel.setSizePolicy(sizePolicy)

        self.BodyVBoxLayout.addWidget(self.TitleLabel)

        self.BodyLabel = BodyLabel(SystemInfoCard)
        self.BodyLabel.setObjectName(u"BodyLabel")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.BodyLabel.sizePolicy().hasHeightForWidth())
        self.BodyLabel.setSizePolicy(sizePolicy1)
        self.BodyLabel.setMaximumSize(QSize(16777215, 101))
        self.BodyLabel.setWordWrap(True)

        self.BodyVBoxLayout.addWidget(self.BodyLabel)


        self.horizontalLayout.addLayout(self.BodyVBoxLayout)

        self.PrimarySplitPushButton = PrimarySplitPushButton(SystemInfoCard)
        self.PrimarySplitPushButton.setObjectName(u"PrimarySplitPushButton")
        self.PrimarySplitPushButton.setMinimumSize(QSize(121, 31))
        self.PrimarySplitPushButton.setMaximumSize(QSize(121, 31))

        self.horizontalLayout.addWidget(self.PrimarySplitPushButton)


        self.retranslateUi(SystemInfoCard)

        QMetaObject.connectSlotsByName(SystemInfoCard)
    # setupUi

    def retranslateUi(self, SystemInfoCard):
        SystemInfoCard.setWindowTitle(QCoreApplication.translate("SystemInfoCard", u"Form", None))
        self.PrimarySplitPushButton.setProperty("text_", QCoreApplication.translate("SystemInfoCard", u"       \u4e0b\u8f7d       ", None))
    # retranslateUi

