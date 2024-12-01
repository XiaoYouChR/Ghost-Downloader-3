# -*- coding: utf-8 -*-

################################################################################
## 你猜是不是 UIC 生成的
##
## Created by: Qt User Interface Compiler version 6.4.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QMetaObject, QSize, Qt)
from PySide6.QtWidgets import (QHBoxLayout, QSizePolicy, QVBoxLayout)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (PixmapLabel, TitleLabel, ToolButton, PrimaryToolButton)

from app.components.icon_label import IconBodyLabel


class Ui_TaskCard(object):
    def setupUi(self, TaskCard):
        if not TaskCard.objectName():
            TaskCard.setObjectName(u"TaskCard")
        TaskCard.resize(793, 100)
        TaskCard.setMinimumSize(QSize(793, 90))
        TaskCard.setMaximumSize(QSize(16777215, 90))
        self.cardHorizontalLayout = QHBoxLayout(TaskCard)
        self.cardHorizontalLayout.setObjectName(u"cardHorizontalLayout")
        self.cardHorizontalLayout.setContentsMargins(18, 8, 18, 8)
        self.cardHorizontalLayout.setSpacing(18)
        self.LogoPixmapLabel = PixmapLabel(TaskCard)
        self.LogoPixmapLabel.setObjectName(u"LogoPixmapLabel")
        self.LogoPixmapLabel.setMinimumSize(QSize(70, 70))
        self.LogoPixmapLabel.setMaximumSize(QSize(70, 70))
        self.LogoPixmapLabel.setScaledContents(True)
        self.LogoPixmapLabel.setAlignment(Qt.AlignCenter)

        self.cardHorizontalLayout.addWidget(self.LogoPixmapLabel)

        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setSpacing(6)

        # self.verticalLayout.addSpacing(15) # 把整体往下撑

        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")

        self.TitleLabel = TitleLabel(TaskCard)
        self.TitleLabel.setObjectName(u"TitleLabel")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.TitleLabel.sizePolicy().hasHeightForWidth())
        self.TitleLabel.setSizePolicy(sizePolicy)
        self.TitleLabel.setMinimumSize(QSize(0, 38))
        self.TitleLabel.setMaximumSize(QSize(16777215, 38))

        self.verticalLayout_2.addWidget(self.TitleLabel)

        # 还需要把 statusHorizonLayout 在 horizonLayout 里面往下撑, 要不然非常难看!
        self.verticalLayout_2.addSpacing(8)

        self.statusHorizonLayout = QHBoxLayout()
        self.statusHorizonLayout.setObjectName(u"statusHorizonLayout")
        self.statusHorizonLayout.setSpacing(8)
        self.speedLabel = IconBodyLabel("下载速度", FIF.SPEED_HIGH, TaskCard)
        self.speedLabel.setObjectName(u"speedLabel")
        self.speedLabel.setMinimumSize(QSize(0, 19))
        self.speedLabel.setMaximumSize(QSize(16777215, 19))

        self.statusHorizonLayout.addWidget(self.speedLabel)

        self.leftTimeLabel = IconBodyLabel("剩余时间", FIF.STOP_WATCH, TaskCard)
        self.leftTimeLabel.setObjectName(u"leftTimeLabel")
        self.leftTimeLabel.setMinimumSize(QSize(0, 19))
        self.leftTimeLabel.setMaximumSize(QSize(16777215, 19))

        self.statusHorizonLayout.addWidget(self.leftTimeLabel)

        self.processLabel = IconBodyLabel("下载进度", FIF.LIBRARY, TaskCard)
        self.processLabel.setObjectName(u"processLabel")
        self.processLabel.setMinimumSize(QSize(0, 19))
        self.processLabel.setMaximumSize(QSize(16777215, 19))

        self.statusHorizonLayout.addWidget(self.processLabel)
        self.statusHorizonLayout.addSpacing(1677215)

        self.verticalLayout_2.addLayout(self.statusHorizonLayout)  # 先加入 后期代码处理

        self.infoHorizonLayout = QHBoxLayout(TaskCard)
        self.infoHorizonLayout.setObjectName(u"infoHorizonLayout")
        self.infoHorizonLayout.setSpacing(8)

        self.infoLabel = IconBodyLabel("若任务初始化过久，请检查网络连接后重试.", FIF.INFO, TaskCard)
        self.infoLabel.setObjectName(u"infoLabel")
        self.infoLabel.setMinimumSize(QSize(0, 19))
        self.infoLabel.setMaximumSize(QSize(16777215, 19))

        self.infoHorizonLayout.addWidget(self.infoLabel)

        self.verticalLayout_2.addLayout(self.infoHorizonLayout)

        self.horizontalLayout.addLayout(self.verticalLayout_2)

        self.pauseButton = PrimaryToolButton(TaskCard)
        self.pauseButton.setObjectName(u"pauseButton")
        self.pauseButton.setMinimumSize(QSize(31, 31))
        self.pauseButton.setMaximumSize(QSize(31, 31))

        self.horizontalLayout.addWidget(self.pauseButton)

        self.folderButton = ToolButton(TaskCard)
        self.folderButton.setObjectName(u"folderButton")
        self.folderButton.setMinimumSize(QSize(31, 31))
        self.folderButton.setMaximumSize(QSize(31, 31))

        self.horizontalLayout.addWidget(self.folderButton)

        self.cancelButton = ToolButton(TaskCard)
        self.cancelButton.setObjectName(u"cancelButton")
        self.cancelButton.setMinimumSize(QSize(31, 31))
        self.cancelButton.setMaximumSize(QSize(31, 31))

        self.horizontalLayout.addWidget(self.cancelButton)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.cardHorizontalLayout.addLayout(self.verticalLayout)

        # 初始化 Icon 类
        self.pauseButton.setIcon(FIF.PAUSE)
        self.cancelButton.setIcon(FIF.DELETE)
        self.folderButton.setIcon(FIF.FOLDER)

        self.retranslateUi(TaskCard)

        QMetaObject.connectSlotsByName(TaskCard)

    # setupUi

    def retranslateUi(self, TaskCard):
        TaskCard.setWindowTitle(QCoreApplication.translate("TaskCard", u"Form", None))
    # retranslateUi
