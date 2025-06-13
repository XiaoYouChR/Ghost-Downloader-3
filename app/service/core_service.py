from PySide6.QtCore import QThread


class CoreService(QThread):
    """单例, 用于管理所有任务, 还有核心的插件注册, 信息同步等，带有 WebSocket"""
    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        """主循环, 不断向客户端还有 WebSocket 发送 TaskManagerInfos"""
        pass
    
    