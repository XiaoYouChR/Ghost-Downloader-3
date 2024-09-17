from qfluentwidgets import CheckBox, MessageBox


class DelDialog(MessageBox):
    def __init__(self, parent=None):
        super().__init__(title="删除下载任务", content="确定要删除下载任务吗？", parent=parent)
        self.setClosableOnMaskClicked(True)

        self.checkBox = CheckBox("彻底删除", self)
        self.textLayout.insertWidget(2, self.checkBox)
