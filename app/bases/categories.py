from pathlib import Path
from typing import Any

# 默认分类规则（纯数据，不依赖 cfg / qfluentwidgets）——引擎按它权威归类，gui 的 category_service 也复用同一份。
# "{default}" 是下载根目录占位；自定义规则编辑器后续，先用这套默认集。
DEFAULT_FOLDER_MACRO = "{default}"

DEFAULT_CATEGORY_PRESETS: list[dict[str, Any]] = [
    {
        "categoryId": "cat_video", "name": "视频", "icon": "VIDEO", "folder": "{default}/Video",
        "extensions": [
            "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "rmvb", "rm",
            "mpg", "mpeg", "mpe", "mpa", "3gp", "ts", "m2ts", "ogv", "asf", "qt",
        ],
    },
    {
        "categoryId": "cat_audio", "name": "音频", "icon": "MUSIC", "folder": "{default}/Audio",
        "extensions": ["mp3", "flac", "wav", "aac", "ogg", "m4a", "wma", "ape", "opus", "mid", "ra", "aif"],
    },
    {
        "categoryId": "cat_image", "name": "图片", "icon": "PHOTO", "folder": "{default}/Images",
        "extensions": [
            "jpg", "jpeg", "png", "gif", "bmp", "webp", "avif", "svg", "tif", "tiff", "ico", "heic", "heif",
        ],
    },
    {
        "categoryId": "cat_subtitle", "name": "字幕", "icon": "CHAT", "folder": "{default}/Subtitles",
        "extensions": ["srt", "ass", "ssa", "sub", "sup", "idx", "vtt", "lrc", "smi", "psb"],
    },
    {
        "categoryId": "cat_document", "name": "文档", "icon": "DOCUMENT", "folder": "{default}/Documents",
        "extensions": [
            "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "epub", "mobi", "azw3",
            "rtf", "odt", "ods", "odp", "md", "csv", "nfo", "chm",
        ],
    },
    {
        "categoryId": "cat_archive", "name": "压缩包", "icon": "ZIP_FOLDER", "folder": "{default}/Archives",
        "extensions": [
            "zip", "rar", "7z", "tar", "gz", "gzip", "bz2", "xz", "tgz", "tbz2", "zst", "ace",
            "arj", "cab", "lzh", "sea", "sit", "sitx", "z", "001",
            "tar.gz", "tar.bz2", "tar.xz", "tar.zst",
        ],
    },
    {
        "categoryId": "cat_program", "name": "程序", "icon": "APPLICATION", "folder": "{default}/Programs",
        "extensions": [
            "exe", "msi", "msu", "msp", "apk", "apks", "apkm", "dmg", "pkg", "deb", "rpm",
            "appimage", "iso", "img", "esd", "wim", "bin", "jar", "bat", "sh", "com",
        ],
    },
    {"categoryId": "cat_other", "name": "其他", "icon": "HELP", "extensions": []},
]


def categoryFolderFor(filename: str, baseFolder: str) -> str:
    """按文件扩展名把下载目录归到分类子目录（如 baseFolder/Video）；无匹配则原样返回 baseFolder。
    tar.gz 这类双后缀先整体匹配再退单后缀，对齐 gui 的 matchByName。"""
    suffixes = [s.lstrip(".").lower() for s in Path(filename).suffixes]
    candidates: list[str] = []
    if len(suffixes) >= 2:
        candidates.append(".".join(suffixes[-2:]))
    if suffixes:
        candidates.append(suffixes[-1])

    for candidate in candidates:
        for preset in DEFAULT_CATEGORY_PRESETS:
            if candidate in preset["extensions"]:
                folder = preset.get("folder")
                return folder.replace(DEFAULT_FOLDER_MACRO, baseFolder) if folder else baseFolder
    return baseFolder
