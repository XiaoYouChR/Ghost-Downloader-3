# -*- coding: utf-8 -*-

################################################################################
## 你猜是不是 UIC 生成的
##
## Created by: Qt User Interface Compiler version 6.4.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QSize, Qt)
from PySide6.QtWidgets import (QHBoxLayout, QSizePolicy, QVBoxLayout)
from qfluentwidgets import FluentIcon as FIF, SubtitleLabel
from qfluentwidgets import (PixmapLabel, ToolButton, PrimaryToolButton)

from app.components.custom_components import IconBodyLabel


class Ui_TaskCard(object):
    def setupUi(self, TaskCard):
        if not TaskCard.objectName():
            TaskCard.setObjectName(u"TaskCard")
        TaskCard.resize(793, 100)
        TaskCard.setFixedHeight(68)

        self.vBoxLayout = QVBoxLayout(TaskCard)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.setContentsMargins(4, 0, 4, 0)

        self.horizontalLayout = QHBoxLayout(TaskCard)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(14, 0, 14, 0)
        self.horizontalLayout.setSpacing(8)
        self.LogoPixmapLabel = PixmapLabel(TaskCard)
        self.LogoPixmapLabel.setObjectName(u"LogoPixmapLabel")
        self.LogoPixmapLabel.setFixedSize(QSize(48, 48))
        self.LogoPixmapLabel.setScaledContents(True)
        self.LogoPixmapLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.horizontalLayout.addWidget(self.LogoPixmapLabel)

        self.verticalLayout = QVBoxLayout() # 放进度条的
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")

        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")

        self.titleLabel = SubtitleLabel(TaskCard)
        self.titleLabel.setObjectName(u"titleLabel")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.titleLabel.setSizePolicy(sizePolicy)
        self.titleLabel.setFixedHeight(38)

        self.verticalLayout_2.addWidget(self.titleLabel)

        self.statusHorizonLayout = QHBoxLayout()
        self.statusHorizonLayout.setObjectName(u"statusHorizonLayout")
        self.statusHorizonLayout.setSpacing(8)
        self.speedLabel = IconBodyLabel("下载速度", FIF.SPEED_HIGH, TaskCard)
        self.speedLabel.setObjectName(u"speedLabel")
        self.speedLabel.setFixedHeight(19)

        self.statusHorizonLayout.addWidget(self.speedLabel)

        self.leftTimeLabel = IconBodyLabel("剩余时间", FIF.STOP_WATCH, TaskCard)
        self.leftTimeLabel.setObjectName(u"leftTimeLabel")
        self.leftTimeLabel.setFixedHeight(19)

        self.statusHorizonLayout.addWidget(self.leftTimeLabel)

        self.progressLabel = IconBodyLabel("下载进度", FIF.LIBRARY, TaskCard)
        self.progressLabel.setObjectName(u"progressLabel")
        self.progressLabel.setFixedHeight(19)

        self.statusHorizonLayout.addWidget(self.progressLabel)
        self.statusHorizonLayout.addSpacing(1677215)

        self.verticalLayout_2.addLayout(self.statusHorizonLayout)  # 先加入 后期代码处理

        self.infoHorizonLayout = QHBoxLayout(TaskCard)
        self.infoHorizonLayout.setObjectName(u"infoHorizonLayout")
        self.infoHorizonLayout.setSpacing(8)

        self.infoLabel = IconBodyLabel("若任务初始化过久，请检查网络连接后重试.", FIF.INFO, TaskCard)
        self.infoLabel.setObjectName(u"infoLabel")
        self.infoLabel.setFixedHeight(19)

        self.infoHorizonLayout.addWidget(self.infoLabel)

        self.verticalLayout_2.addLayout(self.infoHorizonLayout)

        self.horizontalLayout.addLayout(self.verticalLayout_2)

        self.pauseButton = PrimaryToolButton(TaskCard)
        self.pauseButton.setObjectName(u"pauseButton")
        self.pauseButton.setFixedSize(QSize(31, 31))

        self.horizontalLayout.addWidget(self.pauseButton)

        self.folderButton = ToolButton(TaskCard)
        self.folderButton.setObjectName(u"folderButton")
        self.folderButton.setFixedSize(QSize(31, 31))

        self.horizontalLayout.addWidget(self.folderButton)

        self.cancelButton = ToolButton(TaskCard)
        self.cancelButton.setObjectName(u"cancelButton")
        self.cancelButton.setFixedSize(QSize(31, 31))

        self.horizontalLayout.addWidget(self.cancelButton)

        self.vBoxLayout.addLayout(self.horizontalLayout)
        self.vBoxLayout.addLayout(self.verticalLayout)

        # 初始化 Icon 类
        self.pauseButton.setIcon(FIF.PAUSE)
        self.cancelButton.setIcon(FIF.DELETE)
        self.folderButton.setIcon(FIF.FOLDER)
