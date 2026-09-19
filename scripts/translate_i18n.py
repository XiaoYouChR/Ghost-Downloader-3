import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
I18N_DIR = REPO / "app" / "assets" / "i18n"
BROWSER_I18N_DIR = REPO / "browser_extension" / "app" / "public" / "_locales"

COMPOSE_RES_DIR = REPO / "compose" / "app" / "src" / "main" / "res"
ANDROID_SOURCE_FILES = [
    "strings.xml",
    "strings_identity.xml",
    "strings_settings.xml",
    "strings_settings_edit.xml",
    "strings_settings_flow.xml",
    "strings_task_bar.xml",
    "strings_tasks.xml",
]
ANDROID_LOCALE_FOLDERS = {
    "en_US": "values-en",
    "ja_JP": "values-ja",
    "ru_RU": "values-ru",
    "zh_TW": "values-zh-rTW",
    "zh_HK": "values-zh-rHK",
    "pt_BR": "values-pt-rBR",
    "es_ES": "values-es",
}

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"

LOCALES = {
    "en_US": "English (United States)",
    "ja_JP": "日本語 (Japanese)",
    "ru_RU": "Русский (Russian)",
    "zh_HK": "繁體中文 (Hong Kong)",
    "zh_TW": "繁體中文 (Taiwan)",
    "pt_BR": "Português (Brasil)",
    "es_ES": "Español (España)",
}

SYSTEM_PROMPT_DESKTOP = """\
将下载管理器 Ghost Downloader 3 的 UI 文本从简体中文翻译为 {locale_name}。

翻译「待翻译」中的每一条，参考「已有翻译」的术语和语气。
占位符 {{0}} {{1}} 和 HTML 标签原样保留。\\n 保留在译文相同位置。

输出格式与输入相同：=== Context === 分组，每行 源文 = 译文。只输出「待翻译」部分。"""

SYSTEM_PROMPT_BROWSER = """\
将 Ghost Downloader 浏览器扩展的 UI 文本从简体中文翻译为 {locale_name}。

「已有翻译」格式：key = 源文 → 译文（参考术语和语气）
「待翻译」格式：key = 源文（行尾 # 注释是上下文提示，保留原文）

翻译「待翻译」中的每一条。占位符 $1 $2 $NAME$ 原样保留。

输出格式：每行 key = 译文。只输出「待翻译」部分。"""

SYSTEM_PROMPT_ANDROID = """\
将下载管理器 Ghost Downloader 3 的 Android 端 UI 文本从简体中文翻译为 {locale_name}。

翻译「待翻译」中的每一条，参考「已有翻译」的术语和语气。
占位符 %1$s %2$d %d%% 等原样保留。\\n 保留在译文相同位置。

输出格式：每行 name = 译文。只输出「待翻译」部分。"""


def escapeNewlines(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", "\\n")


def unescapeNewlines(s: str) -> str:
    return re.sub(r"\\([n\\])", lambda m: "\n" if m[1] == "n" else "\\", s)


def parseTs(path: Path):
    tree = ET.parse(path)

    finished = []
    unfinished = []

    for ctx in tree.getroot().findall("context"):
        name = ctx.findtext("name") or ""
        for msg in ctx.findall("message"):
            source = msg.findtext("source") or ""
            t = msg.find("translation")
            text = t.text or ""
            if t.get("type") == "unfinished":
                unfinished.append((name, source, text))
            else:
                finished.append((name, source, text))

    return tree, finished, unfinished


def buildPrompt(finished, unfinished) -> str:
    lines = []

    if finished:
        lines.append("## 已有翻译")
        currentContext = None
        for ctx, src, trans in finished:
            if ctx != currentContext:
                lines.append(f"=== {ctx} ===")
                currentContext = ctx
            lines.append(f"{escapeNewlines(src)} = {escapeNewlines(trans)}")
        lines.append("")

    lines.append("## 待翻译")
    currentContext = None
    for ctx, src, existing in unfinished:
        if ctx != currentContext:
            lines.append(f"=== {ctx} ===")
            currentContext = ctx
        rhs = escapeNewlines(existing) if existing else ""
        lines.append(f"{escapeNewlines(src)} = {rhs}")

    return "\n".join(lines)


def fetchTranslation(system: str, user: str) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "reasoning_effort": "low",
    }
    req = Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    with urlopen(req, timeout=600) as resp:
        body = json.loads(resp.read())
    return body["choices"][0]["message"]["content"]


def parseResponse(text: str) -> dict[tuple[str, str], str]:
    translations = {}
    currentContext = ""
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("=== ") and line.endswith(" ==="):
            currentContext = line[4:-4]
            continue
        if " = " in line:
            srcEsc, transEsc = line.split(" = ", 1)
            transEsc = transEsc.strip()
            if transEsc:
                src = unescapeNewlines(srcEsc.strip())
                trans = unescapeNewlines(transEsc)
                translations[(currentContext, src)] = trans
    return translations


def setTranslations(tree: ET.ElementTree, translations: dict) -> int:
    count = 0
    for ctx in tree.getroot().findall("context"):
        name = ctx.findtext("name") or ""
        for msg in ctx.findall("message"):
            t = msg.find("translation")
            if t.get("type") != "unfinished":
                continue
            source = msg.findtext("source") or ""
            key = (name, source)
            if key in translations:
                t.text = translations[key]
                del t.attrib["type"]
                count += 1
    return count


def saveTs(tree: ET.ElementTree, path: Path) -> None:
    ET.indent(tree.getroot(), space="    ")
    raw = ET.tostring(tree.getroot(), encoding="unicode")
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE TS>\n"
        f"{raw}\n",
        encoding="utf-8",
    )


def translateLocale(locale: str, localeName: str) -> None:
    tsPath = I18N_DIR / f"gd3.{locale}.ts"
    if not tsPath.exists():
        print(f"[{locale}] .ts not found — run sync_i18n_res.py first")
        return

    tree, finished, unfinished = parseTs(tsPath)
    if not unfinished:
        print(f"[{locale}] Nothing to translate")
        return

    print(f"[{locale}] {len(unfinished)} unfinished, {len(finished)} reference …")

    system = SYSTEM_PROMPT_DESKTOP.format(locale_name=localeName)
    user = buildPrompt(finished, unfinished)
    print(f"[{locale}] Calling API ({len(user)} chars) …")

    response = fetchTranslation(system, user)
    translations = parseResponse(response)
    count = setTranslations(tree, translations)
    saveTs(tree, tsPath)

    missed = len(unfinished) - count
    status = "done" if missed == 0 else f"done ({missed} missed)"
    print(f"[{locale}] {status}: {count}/{len(unfinished)} filled")


def checkLocales(locales: dict[str, str]) -> int:
    total = 0
    for locale in locales:
        tsPath = I18N_DIR / f"gd3.{locale}.ts"
        if not tsPath.exists():
            print(f"  {locale}: .ts not found")
            continue
        _, _, unfinished = parseTs(tsPath)
        total += len(unfinished)
        if unfinished:
            print(f"  {locale}: {len(unfinished)} unfinished")
        else:
            print(f"  {locale}: up to date")
    return total


def parseBrowserMessages(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def buildBrowserPrompt(
    source: dict[str, dict],
    existing: dict[str, dict],
    untranslated: dict[str, dict],
) -> str:
    lines = []

    if existing:
        lines.append("## 已有翻译")
        for key, entry in existing.items():
            src = source.get(key, {}).get("message", "")
            lines.append(f"{key} = {src} → {entry['message']}")
        lines.append("")

    lines.append("## 待翻译")
    for key, entry in untranslated.items():
        desc = entry.get("description")
        hint = f"  # {desc}" if desc else ""
        lines.append(f"{key} = {entry['message']}{hint}")

    return "\n".join(lines)


def parseBrowserResponse(text: str) -> dict[str, str]:
    translations = {}
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if " = " in line:
            key, trans = line.split(" = ", 1)
            trans = trans.strip()
            if trans:
                translations[key.strip()] = trans
    return translations


BROWSER_LOCALE_MAP = {
    "en_US": "en_US",
    "ja_JP": "ja",
    "ru_RU": "ru",
    "zh_HK": "zh_HK",
    "zh_TW": "zh_TW",
    "pt_BR": "pt_BR",
}


def translateBrowserLocale(locale: str, localeName: str) -> None:
    chromeLocale = BROWSER_LOCALE_MAP.get(locale, locale)
    sourceDir = BROWSER_I18N_DIR / "zh_CN"
    targetDir = BROWSER_I18N_DIR / chromeLocale

    source = parseBrowserMessages(sourceDir / "messages.json")
    if not source:
        print(f"[browser:{locale}] source messages.json not found")
        return

    existing = parseBrowserMessages(targetDir / "messages.json")
    untranslated = {k: v for k, v in source.items() if k not in existing}
    if not untranslated:
        print(f"[browser:{locale}] Nothing to translate")
        return

    print(f"[browser:{locale}] {len(untranslated)} untranslated, {len(existing)} reference …")

    system = SYSTEM_PROMPT_BROWSER.format(locale_name=localeName)
    user = buildBrowserPrompt(source, existing, untranslated)
    print(f"[browser:{locale}] Calling API ({len(user)} chars) …")

    response = fetchTranslation(system, user)
    translations = parseBrowserResponse(response)

    merged = {**existing}
    filled = 0
    for key, trans in translations.items():
        if key in source:
            merged[key] = {"message": trans}
            if desc := source[key].get("description"):
                merged[key]["description"] = desc
            filled += 1

    targetDir.mkdir(parents=True, exist_ok=True)
    (targetDir / "messages.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    missed = len(untranslated) - filled
    status = "done" if missed == 0 else f"done ({missed} missed)"
    print(f"[browser:{locale}] {status}: {filled}/{len(untranslated)} filled")


def checkBrowserLocales(locales: dict[str, str]) -> int:
    total = 0
    source = parseBrowserMessages(BROWSER_I18N_DIR / "zh_CN" / "messages.json")
    if not source:
        print("  browser: source messages.json not found")
        return 0
    for locale in locales:
        chromeLocale = BROWSER_LOCALE_MAP.get(locale, locale)
        existing = parseBrowserMessages(BROWSER_I18N_DIR / chromeLocale / "messages.json")
        missing = len(source) - len(existing)
        total += max(missing, 0)
        if missing > 0:
            print(f"  browser:{locale}: {missing} untranslated")
        else:
            print(f"  browser:{locale}: up to date")
    return total


def parseAndroidStrings(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    root = ET.parse(path).getroot()
    entries = {}
    for elem in root.findall("string"):
        if elem.get("translatable") == "false":
            continue
        name = elem.get("name")
        text = elem.text or ""
        if name and text:
            entries[name] = text
    return entries


def buildAndroidPrompt(
    existing: dict[str, tuple[str, str]],
    untranslated: dict[str, tuple[str, str]],
) -> str:
    lines = []
    if existing:
        lines.append("## 已有翻译")
        currentFile = None
        for name, (fname, text) in existing.items():
            if fname != currentFile:
                lines.append(f"=== {fname} ===")
                currentFile = fname
            lines.append(f"{name} = {escapeNewlines(text)}")
        lines.append("")

    lines.append("## 待翻译")
    currentFile = None
    for name, (fname, text) in untranslated.items():
        if fname != currentFile:
            lines.append(f"=== {fname} ===")
            currentFile = fname
        lines.append(f"{name} = {escapeNewlines(text)}")

    return "\n".join(lines)


def parseAndroidResponse(text: str) -> dict[str, str]:
    translations = {}
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("==="):
            continue
        if " = " in line:
            name, trans = line.split(" = ", 1)
            trans = trans.strip()
            if trans:
                translations[name.strip()] = unescapeNewlines(trans)
    return translations


def escapeAndroidXml(text: str) -> str:
    for old, new in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"),
                     ("'", "\\'"), ('"', '\\"')):
        text = text.replace(old, new)
    return text


def translateAndroidLocale(locale: str, localeName: str) -> None:
    folder = ANDROID_LOCALE_FOLDERS.get(locale)
    if not folder:
        print(f"[android:{locale}] No folder mapping")
        return

    sourceDir = COMPOSE_RES_DIR / "values"
    localeDir = COMPOSE_RES_DIR / folder

    allSource: dict[str, tuple[str, str]] = {}
    allExisting: dict[str, tuple[str, str]] = {}
    untranslated: dict[str, tuple[str, str]] = {}

    for fname in ANDROID_SOURCE_FILES:
        source = parseAndroidStrings(sourceDir / fname)
        existing = parseAndroidStrings(localeDir / fname)
        for name, text in source.items():
            allSource[name] = (fname, text)
            if name in existing:
                allExisting[name] = (fname, existing[name])
            else:
                untranslated[name] = (fname, text)

    if not untranslated:
        print(f"[android:{locale}] Nothing to translate")
        return

    print(f"[android:{locale}] {len(untranslated)} untranslated, {len(allExisting)} reference …")

    system = SYSTEM_PROMPT_ANDROID.format(locale_name=localeName)
    user = buildAndroidPrompt(allExisting, untranslated)
    print(f"[android:{locale}] Calling API ({len(user)} chars) …")

    response = fetchTranslation(system, user)
    translations = parseAndroidResponse(response)

    fileEntries: dict[str, dict[str, str]] = {}
    filled = 0
    for name, trans in translations.items():
        if name in allSource:
            fname = allSource[name][0]
            fileEntries.setdefault(fname, {})
            fileEntries[fname][name] = trans
            filled += 1

    localeDir.mkdir(parents=True, exist_ok=True)
    for fname in ANDROID_SOURCE_FILES:
        source = parseAndroidStrings(sourceDir / fname)
        existing = parseAndroidStrings(localeDir / fname)
        newTranslations = fileEntries.get(fname, {})
        merged = {**existing, **newTranslations}
        final = {k: v for k, v in merged.items() if k in source}
        if not final:
            continue
        xmlLines = ["<?xml version=\"1.0\" encoding=\"utf-8\"?>", "<resources>"]
        for name in sorted(final):
            text = escapeAndroidXml(final[name])
            xmlLines.append(f'    <string name="{name}">{text}</string>')
        xmlLines.append("</resources>")
        (localeDir / fname).write_text("\n".join(xmlLines) + "\n", encoding="utf-8")

    missed = len(untranslated) - filled
    status = "done" if missed == 0 else f"done ({missed} missed)"
    print(f"[android:{locale}] {status}: {filled}/{len(untranslated)} filled")


def checkAndroidLocales(locales: dict[str, str]) -> int:
    total = 0
    sourceDir = COMPOSE_RES_DIR / "values"
    for locale in locales:
        folder = ANDROID_LOCALE_FOLDERS.get(locale)
        if not folder:
            continue
        localeDir = COMPOSE_RES_DIR / folder
        missing = 0
        for fname in ANDROID_SOURCE_FILES:
            source = parseAndroidStrings(sourceDir / fname)
            existing = parseAndroidStrings(localeDir / fname)
            missing += len(set(source) - set(existing))
        total += missing
        if missing > 0:
            print(f"  android:{locale}: {missing} untranslated")
        else:
            print(f"  android:{locale}: up to date")
    return total


def main() -> int:
    args = sys.argv[1:]
    check = "--check" in args
    browser = "--browser" in args
    android = "--android" in args
    targets = [a for a in args if not a.startswith("-")]

    if targets:
        invalid = [t for t in targets if t not in LOCALES]
        if invalid:
            print(f"Unknown locales: {', '.join(invalid)}", file=sys.stderr)
            print(f"Available: {', '.join(LOCALES)}", file=sys.stderr)
            return 1
        locales = {k: LOCALES[k] for k in targets}
    else:
        locales = LOCALES

    if check:
        if android:
            total = checkAndroidLocales(locales)
        elif browser:
            total = checkBrowserLocales(locales)
        else:
            total = checkLocales(locales)
        return 0 if total == 0 else 2

    if not API_KEY:
        print("Set DEEPSEEK_API_KEY environment variable", file=sys.stderr)
        return 1

    if android:
        translateFn = translateAndroidLocale
    elif browser:
        translateFn = translateBrowserLocale
    else:
        translateFn = translateLocale

    failed = False
    with ThreadPoolExecutor(max_workers=len(locales)) as pool:
        futures = {
            pool.submit(translateFn, loc, name): loc
            for loc, name in locales.items()
        }
        for fut in as_completed(futures):
            loc = futures[fut]
            try:
                fut.result()
            except Exception as exc:
                failed = True
                print(f"[{loc}] ERROR: {exc}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
