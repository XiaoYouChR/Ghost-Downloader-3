import shutil

from app.view.components.cards import UniversalTaskCard


class InstallTaskCard(UniversalTaskCard):
    """供 buildToolInstallTask 创建的安装任务通用，删除时清理整个安装目录。"""

    def onTaskDeleted(self, completely: bool = False):
        if not completely:
            return

        installFolder = self.task.metadata.get("installFolder")
        if installFolder:
            shutil.rmtree(installFolder, ignore_errors=True)
            return

        super().onTaskDeleted(completely)
