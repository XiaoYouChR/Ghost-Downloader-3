from PySide6.QtCore import QCoreApplication, QT_TRANSLATE_NOOP as N


def toLocalizedError(message: str, params: dict | None = None) -> str:
    text = QCoreApplication.translate("TaskErrors", message) or message
    return text.format_map(params) if params else text


N("TaskErrors", "{name} 未安装，请在设置中安装")
N("TaskErrors", "服务器返回了错误（{status}）")
N("TaskErrors", "无法建立 FTP 连接")
N("TaskErrors", "进程异常退出（{code}）：{detail}")
N("TaskErrors", "发生了意外错误：{detail}")

N("UpdateErrors", "无法获取版本信息")
N("UpdateErrors", "校验失败")
N("UpdateErrors", "当前平台无可用更新")
N("UpdateErrors", "DMG 中未找到 .app")
