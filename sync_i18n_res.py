import os
import subprocess


EXCLUDED_FILES = {
    os.path.normpath("./app/assets/resources.py"),
}

def getPyFiles(rootDir):
    """
    递归获取目录下所有.py文件的相对路径
    Args:
        rootDir: 要搜索的根目录
    Returns:
        list: 包含所有.py文件相对路径的列表
    """
    pyFiles = []

    for root, dirs, files in os.walk(rootDir):
        for file in files:
            if file.endswith('.py'):
                # 获取相对路径并确保跨平台兼容性
                relPath = os.path.relpath(os.path.join(root, file), rootDir)
                # 使用os.path.join确保路径分隔符正确
                fullPath = os.path.normpath(os.path.join('.', rootDir, relPath))
                if fullPath not in EXCLUDED_FILES:
                    pyFiles.append(fullPath)

    return sorted(pyFiles)

if __name__ == '__main__':
    appDir = 'app'  # 目标目录
    pyFiles = getPyFiles(appDir)
    pyFiles.extend(getPyFiles('features'))

    # targetLanguages = ["lzh", "en_US", "ja_JP"]
    targetLanguages = ["en_US", "ja_JP", "zh_TW", "zh_HK", "ru_RU"]   # 由于 Qt Bug, 暂时使用 zh_MO 代替 lzh

    for targetLanguage in targetLanguages:
        tsPath = os.path.join("app", "assets", "i18n", f"gd3.{targetLanguage}.ts")
        os.makedirs(os.path.dirname(tsPath), exist_ok=True)

        args = ["-no-ui-lines",
                "-source-language", "zh_CN",
                "-target-language", targetLanguage]

        args.extend(pyFiles)
        args.append("-ts")
        args.append(tsPath)
        result = subprocess.run(["pyside6-lupdate", *args], check=False)
        if result.returncode != 0:
            raise SystemExit(result.returncode)
