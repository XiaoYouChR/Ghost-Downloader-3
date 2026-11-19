def N(context, text):
    return text


# 只放 Qt 本地名称不合适的语言
LANGUAGE_TEXTS = {
    "zh_CN": "简体中文 (中国大陆)",
    "zh_TW": "正體中文 (台灣)",
    "yue_HK": "粤语 (香港)",
    "en_US": "English (US)",
    "ja_JP": "日本語 (日本)",
    "ru_RU": "Русский (Россия)",
    "pt_BR": "Português (Brasil)",
    "es_ES": "Español (España)",
    "id_ID": "Bahasa Indonesia",
}


def loadLanguages() -> list[str]:
    from PySide6.QtCore import QDir
    names = QDir(":/i18n").entryList(["gd3.*_*.qm"])
    codes = sorted(name.removeprefix("gd3.").removesuffix(".qm") for name in names)
    # 粤语的设置值是 yue_HK，文件却叫 zh_HK
    return ["yue_HK" if code == "zh_HK" else code for code in codes]


def toLanguageText(code: str) -> str:
    if code in LANGUAGE_TEXTS:
        return LANGUAGE_TEXTS[code]
    from PySide6.QtCore import QLocale
    locale = QLocale(code)
    name = locale.nativeLanguageName()
    return f"{name[:1].upper()}{name[1:]} ({locale.nativeTerritoryName()})"


def toLocalizedError(error) -> str:
    from PySide6.QtCore import QCoreApplication
    text = QCoreApplication.translate("TaskErrors", error.message) or error.message
    return text.format_map(error.params) if error.params else text


N("TaskErrors", "进程异常退出（{code}）：{detail}")
N("TaskErrors", "发生了意外错误：{detail}")
N("TaskErrors", "不支持该链接")
N("TaskErrors", "压缩包包含不安全路径：{path}")
N("TaskErrors", "压缩包未找到：{path}")
N("TaskErrors", "不支持的压缩格式：{name}")
N("TaskErrors", "解压后未找到可执行文件：{name}")
N("TaskErrors", "无法读取校验文件：{path}")
N("TaskErrors", "无法读取文件：{detail}")
N("TaskErrors", "无法写入文件夹 {folder}：{reason}")
N("TaskErrors", "SHA256 校验失败：期望 {expected}，实际 {actual}")
N("TaskErrors", "下载的文件未找到：{path}")
N("TaskErrors", "无法获取 {name} 的最新 release")
N("TaskErrors", "无法获取 {name}/{branch}/{path}")
N("TaskErrors", "无法下载 {name}/{branch}/{path}")
N("TaskErrors", "无法下载 {name}/{tag}/{asset}")
N("TaskErrors", "无法获取 PyPI 包信息: {package}")
N("TaskErrors", "{name} 未安装，请在设置中安装")

N("TaskErrors", "无法获取版本信息")
N("TaskErrors", "校验失败")
N("TaskErrors", "当前平台无可用更新")
N("TaskErrors", "{path} 已被其他文件占用")
N("TaskErrors", "未获得管理员授权")
N("TaskErrors", "DMG 中未找到 .app")

N("TaskErrors", "端口 {port} 被占用，请更换端口")
N("TaskErrors", "没有权限监听端口 {port}，请更换端口")
N("TaskErrors", "无法监听端口 {port}，详情见日志")
N("TaskErrors", "该链接不能用于更换")
N("TaskErrors", "新链接的内容与原任务不同，请重新添加任务")
