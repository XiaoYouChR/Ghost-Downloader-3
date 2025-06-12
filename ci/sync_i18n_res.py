import os
import sys

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
                fullPath = os.path.join('.', 'app', relPath)
                pyFiles.append(fullPath)
    
    return pyFiles

if __name__ == '__main__':
    appDir = 'app'  # 目标目录
    pyFiles = getPyFiles(appDir)

    # targetLanguages = ["lzh", "en_US", "ja_JP"]
    targetLanguages = ["zh_MO", "en_US", "ja_JP", "zh_TW"]   # 由于 Qt Bug, 暂时使用 zh_MO 代替 lzh

    for targetLanguage in targetLanguages:

        args = ["-no-ui-lines",
                "-source-language", "zh_CN",
                "-target-language", targetLanguage]

        if sys.platform == "win32":
            args.extend(pyFiles)
            args.append("-ts")
            args.append(f"resources/i18n/gd3.{targetLanguage}.ts")
            os.system("pyside6-lupdate " + " ".join(args))
