from PySide6.QtWidgets import (QHBoxLayout)

from qfluentwidgets import (LineEdit, PrimaryToolButton, RadioButton, SubtitleLabel, FluentIcon)

class Ui_PlanTaskDialog(object):
    def setupUi(self, viewLayout):
        viewLayout.setSpacing(10)
        viewLayout.setObjectName(u"verticalLayout")
        viewLayout.setContentsMargins(26, 16, 26, 18)
        self.SubtitleLabel = SubtitleLabel(self)
        self.SubtitleLabel.setObjectName(u"SubtitleLabel")

        viewLayout.addWidget(self.SubtitleLabel)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.powerOffButton = RadioButton(self)
        self.powerOffButton.setObjectName(u"powerOffButton")

        self.horizontalLayout.addWidget(self.powerOffButton)

        self.quitButton = RadioButton(self)
        self.quitButton.setObjectName(u"quitButton")

        self.horizontalLayout.addWidget(self.quitButton)


        viewLayout.addLayout(self.horizontalLayout)

        self.openFileButton = RadioButton(self)
        self.openFileButton.setObjectName(u"openFileButton")

        viewLayout.addWidget(self.openFileButton)

        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.filePathEdit = LineEdit(self)
        self.filePathEdit.setObjectName(u"filePathEdit")
        self.filePathEdit.setEnabled(False)

        self.horizontalLayout_3.addWidget(self.filePathEdit)

        self.selectFileButton = PrimaryToolButton(self)
        self.selectFileButton.setObjectName(u"selectFileButton")
        self.selectFileButton.setEnabled(False)
        self.selectFileButton.setIcon(FluentIcon.FOLDER)

        self.horizontalLayout_3.addWidget(self.selectFileButton)


        viewLayout.addLayout(self.horizontalLayout_3)

        self.retranslateUi()
    # setupUi

    def retranslateUi(self):
        self.SubtitleLabel.setText(self.tr("设置计划任务"))
        self.powerOffButton.setText(self.tr("关机"))
        self.quitButton.setText(self.tr("退出程序"))
        self.openFileButton.setText(self.tr("打开"))
    # retranslateUi

