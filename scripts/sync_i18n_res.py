import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO / "app" / "assets"
I18N_DIR = ASSETS_DIR / "i18n"
QRC_PATH = ASSETS_DIR / "resources.qrc"
RESOURCES_RCC = ASSETS_DIR / "resources.rcc"

SOURCE_LOCALE = "zh_CN"
FALLBACK_LOCALE = "en_US"
# Qt 按系统语言查 gd3.yue 找粤语，Crowdin 导出的粤语文件却叫 zh_HK
EXTRA_FAMILY_ALIASES = {"yue": "zh_HK"}

ENGINE_CONTEXTS = [
    "TaskErrors", "BinaryRuntime", "TaskState",
    "TrackBar", "YtDlpDraftCard", "StreamSelectCard",
    "Categories", "Presets",
]

ANDROID_RES_DIR = REPO / "android" / "app" / "src" / "main" / "res"
ANDROID_I18N_KT = (
    REPO / "android" / "app" / "src" / "main" / "java" / "com" / "xychr"
    / "ghostdownloader" / "i18n" / "EngineStrings.kt"
)
ANDROID_STRINGS_FILE = "strings_engine.xml"
ANDROID_FALLBACK_FILE = "strings_fallback.xml"
# Android 资源目录沿用 Java 的旧语言代码
ANDROID_LANGUAGE_CODES = {"id": "in"}


def findTool(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    candidate = Path(sys.executable).resolve().with_name(
        f"{name}{'.exe' if os.name == 'nt' else ''}")
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError(f"Required tool not found in PATH: {name}")


def findSources() -> list[str]:
    sources = []
    for root in ("app", "features"):
        for path in sorted((REPO / root).rglob("*.py")):
            sources.append(path.relative_to(REPO).as_posix())
    return sources


def findLocales() -> list[str]:
    return sorted(path.name.removeprefix("gd3.").removesuffix(".ts")
                  for path in I18N_DIR.glob("gd3.*.ts"))


def updateSourceTs(sources: list[str]) -> None:
    subprocess.run([
        findTool("pyside6-lupdate"),
        "-tr-function-alias", "QT_TRANSLATE_NOOP+=N",
        "-no-ui-lines",
        "-no-obsolete",
        "-source-language", SOURCE_LOCALE,
        "-target-language", SOURCE_LOCALE,
        *sources,
        "-ts", (I18N_DIR / f"gd3.{SOURCE_LOCALE}.ts").as_posix(),
    ], cwd=REPO, check=True)


def loadTranslations(locale: str) -> dict[tuple[str, str], str]:
    entries = {}
    root = ET.parse(I18N_DIR / f"gd3.{locale}.ts").getroot()
    for context in root.findall("context"):
        contextName = context.findtext("name")
        for message in context.findall("message"):
            node = message.find("translation")
            if node is None or node.get("type") or not (node.text or "").strip():
                continue
            entries[(contextName, message.findtext("source") or "")] = node.text
    return entries


def buildFilledTs(locale: str, fallback: dict[tuple[str, str], str], folder: Path) -> Path:
    translations = loadTranslations(locale)
    tree = ET.parse(I18N_DIR / f"gd3.{SOURCE_LOCALE}.ts")
    tree.getroot().set("language", locale)
    for context in tree.getroot().findall("context"):
        contextName = context.findtext("name")
        for message in context.findall("message"):
            node = message.find("translation")
            key = (contextName, message.findtext("source") or "")
            text = translations.get(key) or fallback.get(key)
            if text:
                node.text = text
                node.attrib.pop("type", None)
    path = folder / f"gd3.{locale}.ts"
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path


def buildQmFiles(locales: list[str]) -> None:
    lrelease = findTool("pyside6-lrelease")
    fallback = loadTranslations(FALLBACK_LOCALE)
    with tempfile.TemporaryDirectory() as folder:
        for locale in locales:
            isBase = locale in (SOURCE_LOCALE, FALLBACK_LOCALE)
            ts = buildFilledTs(locale, {} if isBase else fallback, Path(folder))
            qm = I18N_DIR / f"gd3.{locale}.qm"
            subprocess.run([lrelease, "-nounfinished", ts.as_posix(), "-qm", qm.as_posix()],
                           cwd=REPO, check=True)


def updateQrcI18n(locales: list[str]) -> None:
    families = {}
    for locale in locales:
        families.setdefault(locale.split("_")[0], locale)
    families.update(EXTRA_FAMILY_ALIASES)

    lines = [f'    <file alias="gd3.{locale}.qm">i18n/gd3.{locale}.qm</file>' for locale in locales]
    lines += [f'    <file alias="gd3.{family}.qm">i18n/gd3.{locale}.qm</file>'
              for family, locale in families.items()]
    section = '\n  <qresource prefix="i18n">\n' + "\n".join(lines) + '\n  </qresource>'

    text = QRC_PATH.read_text(encoding="utf-8")
    text = re.sub(r'\s*<qresource prefix="i18n">.*?</qresource>', '', text, flags=re.DOTALL)
    text = text.replace("</RCC>", f"{section}\n</RCC>")
    QRC_PATH.write_text(text, encoding="utf-8")


def toAndroidFolder(locale: str) -> Path | None:
    if locale == SOURCE_LOCALE:
        return ANDROID_RES_DIR / "values"
    language, _, region = locale.partition("_")
    language = ANDROID_LANGUAGE_CODES.get(language, language)
    for name in (f"values-{language}-r{region}", f"values-{language}"):
        if (ANDROID_RES_DIR / name / "strings.xml").exists():
            return ANDROID_RES_DIR / name
    return None


def loadEngineCatalog(locale: str, fallback: dict[tuple[str, str], str]) -> dict[str, tuple[str, str, str]]:
    translations = loadTranslations(locale)
    entries = {}
    root = ET.parse(I18N_DIR / f"gd3.{SOURCE_LOCALE}.ts").getroot()
    for context in root.findall("context"):
        contextName = context.findtext("name")
        if contextName not in ENGINE_CONTEXTS:
            continue
        for message in context.findall("message"):
            source = message.findtext("source") or ""
            key = (contextName, source)
            text = source if locale == SOURCE_LOCALE else translations.get(key) or fallback.get(key)
            if source and text:
                digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
                entries[f"engine_{contextName.lower()}_{digest}"] = (contextName, source, text.strip())
    return entries


def escapeAndroidString(text: str) -> str:
    for old, new in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"),
                     ("'", "\\'"), ('"', '\\"')):
        text = text.replace(old, new)
    return text


def buildAndroidEngineStrings(locales: list[str]) -> None:
    fallback = loadTranslations(FALLBACK_LOCALE)
    source = loadEngineCatalog(SOURCE_LOCALE, fallback)
    if not source:
        raise SystemExit(f"No messages found for contexts {ENGINE_CONTEXTS}")

    nameToSource = {}
    for name, (_, text, _) in source.items():
        if name in nameToSource:
            raise SystemExit(f"resourceName collision: {text!r} vs {nameToSource[name]!r}")
        nameToSource[name] = text

    for locale in locales:
        folder = toAndroidFolder(locale)
        if folder is None:
            continue
        entries = loadEngineCatalog(locale, fallback)
        xmlLines = ["<!-- Generated by scripts/sync_i18n_res.py -->", "<resources>"]
        for resource in sorted(entries):
            text = escapeAndroidString(entries[resource][2])
            xmlLines.append(f'    <string name="{resource}" formatted="false">{text}</string>')
        xmlLines.append("</resources>")
        (folder / ANDROID_STRINGS_FILE).write_text("\n".join(xmlLines) + "\n", encoding="utf-8")

    ktLines = [
        "// Generated by scripts/sync_i18n_res.py",
        "package com.xychr.ghostdownloader.i18n",
        "",
        "import com.xychr.ghostdownloader.R",
        "",
        "internal val engineStrings: Map<String, Int> = mapOf(",
    ]
    for resource in sorted(source):
        contextName, rawText, _ = source[resource]
        text = rawText.replace("\\", "\\\\").replace('"', '\\"')
        ktLines.append(f'    "{contextName}:{text}" to R.string.{resource},')
        ktLines.append(f'    "{text}" to R.string.{resource},')
    ktLines.append(")")
    ANDROID_I18N_KT.parent.mkdir(parents=True, exist_ok=True)
    ANDROID_I18N_KT.write_text("\n".join(ktLines) + "\n", encoding="utf-8")


def loadAndroidResources(folder: Path) -> dict[str, ET.Element]:
    resources = {}
    for path in sorted(folder.glob("strings*.xml")):
        if path.name in (ANDROID_STRINGS_FILE, ANDROID_FALLBACK_FILE):
            continue
        for element in ET.parse(path).getroot():
            if element.tag in ("string", "plurals") and element.get("translatable") != "false":
                resources[element.get("name")] = element
    return resources


def buildAndroidFallbackStrings(locales: list[str]) -> None:
    fallbackFolder = toAndroidFolder(FALLBACK_LOCALE)
    if fallbackFolder is None:
        return
    fallback = loadAndroidResources(fallbackFolder)
    for locale in locales:
        folder = toAndroidFolder(locale)
        if folder is None or locale in (SOURCE_LOCALE, FALLBACK_LOCALE):
            continue
        existing = loadAndroidResources(folder)
        missing = [fallback[name] for name in sorted(fallback) if name not in existing]
        path = folder / ANDROID_FALLBACK_FILE
        if not missing:
            path.unlink(missing_ok=True)
            continue
        xmlLines = ["<!-- Generated by scripts/sync_i18n_res.py -->", "<resources>"]
        xmlLines += ["    " + ET.tostring(element, encoding="unicode").strip() for element in missing]
        xmlLines.append("</resources>")
        path.write_text("\n".join(xmlLines) + "\n", encoding="utf-8")


def buildResources() -> None:
    # 格式 2 起记录文件修改时间，CI 每次 checkout 都会让 .rcc 变化
    subprocess.run([
        findTool("pyside6-rcc"), "--binary", "--format-version", "1",
        "-o", RESOURCES_RCC.as_posix(),
        QRC_PATH.as_posix(),
    ], cwd=REPO, check=True)


def main() -> int:
    updateSourceTs(findSources())
    locales = findLocales()
    buildQmFiles(locales)
    updateQrcI18n(locales)
    if ANDROID_RES_DIR.exists():
        buildAndroidEngineStrings(locales)
        buildAndroidFallbackStrings(locales)
    buildResources()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
