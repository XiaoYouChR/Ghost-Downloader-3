# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'TaskCard.ui'
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
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)

from qfluentwidgets import (BodyLabel, CardWidget, PixmapLabel, ProgressBar,
                            PushButton, TitleLabel, ToolButton, PrimaryToolButton)

class Ui_TaskCard(object):
    def setupUi(self, TaskCard):
        if not TaskCard.objectName():
            TaskCard.setObjectName(u"TaskCard")
        TaskCard.resize(793, 119)
        TaskCard.setMinimumSize(QSize(793, 119))
        TaskCard.setMaximumSize(QSize(16777215, 119))
        self.horizontalLayout_3 = QHBoxLayout(TaskCard)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.LogoPixmapLabel = PixmapLabel(TaskCard)
        self.LogoPixmapLabel.setObjectName(u"LogoPixmapLabel")
        self.LogoPixmapLabel.setMinimumSize(QSize(101, 101))
        self.LogoPixmapLabel.setMaximumSize(QSize(101, 101))
        self.LogoPixmapLabel.setScaledContents(True)
        self.LogoPixmapLabel.setAlignment(Qt.AlignCenter)

        self.horizontalLayout_3.addWidget(self.LogoPixmapLabel)

        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.TitleLabel = TitleLabel(TaskCard)
        self.TitleLabel.setObjectName(u"TitleLabel")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.TitleLabel.sizePolicy().hasHeightForWidth())
        self.TitleLabel.setSizePolicy(sizePolicy)
        self.TitleLabel.setMinimumSize(QSize(0, 38))
        self.TitleLabel.setMaximumSize(QSize(16777215, 38))

        self.verticalLayout.addWidget(self.TitleLabel)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setSpacing(6)
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.pauseButton = ToolButton(TaskCard)
        self.pauseButton.setObjectName(u"pauseButton")
        self.pauseButton.setMinimumSize(QSize(31, 31))
        self.pauseButton.setMaximumSize(QSize(31, 31))

        self.horizontalLayout.addWidget(self.pauseButton)

        # self.cancelButton = ToolButton(TaskCard)
        # self.cancelButton.setObjectName(u"cancelButton")
        # self.cancelButton.setMinimumSize(QSize(31, 31))
        # self.cancelButton.setMaximumSize(QSize(31, 31))

        # self.horizontalLayout.addWidget(self.cancelButton)

        self.folderButton = PrimaryToolButton(TaskCard)
        self.folderButton.setObjectName(u"folderButton")
        self.folderButton.setMinimumSize(QSize(31, 31))
        self.folderButton.setMaximumSize(QSize(31, 31))

        self.horizontalLayout.addWidget(self.folderButton)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.speedLable = BodyLabel(TaskCard)
        self.speedLable.setObjectName(u"speedLable")
        self.speedLable.setMinimumSize(QSize(0, 19))
        self.speedLable.setMaximumSize(QSize(151, 19))

        self.horizontalLayout_2.addWidget(self.speedLable)

        self.leftTimeLabel = BodyLabel(TaskCard)
        self.leftTimeLabel.setObjectName(u"leftTimeLabel")
        self.leftTimeLabel.setMinimumSize(QSize(0, 19))
        self.leftTimeLabel.setMaximumSize(QSize(151, 19))

        self.horizontalLayout_2.addWidget(self.leftTimeLabel)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer_2)

        self.processLabel = BodyLabel(TaskCard)
        self.processLabel.setObjectName(u"processLabel")
        self.processLabel.setMinimumSize(QSize(0, 19))
        self.processLabel.setMaximumSize(QSize(201, 19))

        self.horizontalLayout_2.addWidget(self.processLabel)


        self.verticalLayout.addLayout(self.horizontalLayout_2)

        self.ProgressBar = ProgressBar(TaskCard)
        self.ProgressBar.setObjectName(u"ProgressBar")

        self.verticalLayout.addWidget(self.ProgressBar)


        self.horizontalLayout_3.addLayout(self.verticalLayout)


        self.retranslateUi(TaskCard)

        QMetaObject.connectSlotsByName(TaskCard)
    # setupUi

    def retranslateUi(self, TaskCard):
        TaskCard.setWindowTitle(QCoreApplication.translate("TaskCard", u"Form", None))
        self.pauseButton.setText("")
        # self.cancelButton.setText("")
        self.folderButton.setText("")
        self.processLabel.setText("")
    # retranslateUi

