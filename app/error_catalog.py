from PySide6.QtCore import QCoreApplication, QT_TRANSLATE_NOOP as N


def toLocalizedError(message: str, params: dict | None = None) -> str:
    text = QCoreApplication.translate("TaskErrors", message) or message
    return text.format_map(params) if params else text


N("TaskErrors", "进程异常退出（{code}）：{detail}")
N("TaskErrors", "发生了意外错误：{detail}")
N("TaskErrors", "压缩包包含不安全路径：{path}")
N("TaskErrors", "压缩包未找到：{path}")
N("TaskErrors", "不支持的压缩格式：{name}")
N("TaskErrors", "解压后未找到可执行文件：{name}")
N("TaskErrors", "无法读取校验文件：{path}")
N("TaskErrors", "SHA256 校验失败：期望 {expected}，实际 {actual}")
N("TaskErrors", "下载的文件未找到：{path}")
N("TaskErrors", "无法获取 {name} 的最新 release")
N("TaskErrors", "无法获取 {name}/{branch}/{path}")
N("TaskErrors", "无法下载 {name}/{branch}/{path}")
N("TaskErrors", "无法下载 {name}/{tag}/{asset}")
N("TaskErrors", "无法获取 PyPI 包信息: {package}")

N("UpdateErrors", "无法获取版本信息")
N("UpdateErrors", "校验失败")
N("UpdateErrors", "当前平台无可用更新")
N("UpdateErrors", "DMG 中未找到 .app")
