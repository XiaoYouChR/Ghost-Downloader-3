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
}

SYSTEM_PROMPT = """\
你是专业软件本地化译员。将下载管理器 "Ghost Downloader 3" 的 UI 文本从简体中文译为 {locale_name}。

规则:
1. 占位符 {{0}} {{1}} {{2}} 等必须原样保留，位置和数量不变
2. HTML 标签原样保留
3. \\n 表示换行，保留在译文相同位置
4. 参考「已有翻译」的术语和语气
5. 严格保持 === Context === 分组 + "源文 = 译文" 格式输出
6. 只输出待翻译部分的结果
7. 不要输出解释、注释、markdown 标记"""


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
        "max_tokens": 16384,
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

    system = SYSTEM_PROMPT.format(locale_name=localeName)
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


def main() -> int:
    args = sys.argv[1:]
    check = "--check" in args
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
        total = checkLocales(locales)
        return 0 if total == 0 else 2

    if not API_KEY:
        print("Set DEEPSEEK_API_KEY environment variable", file=sys.stderr)
        return 1

    failed = False
    with ThreadPoolExecutor(max_workers=len(locales)) as pool:
        futures = {
            pool.submit(translateLocale, loc, name): loc
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
