from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from PySide6.QtCore import QLocale

REPO = Path(__file__).resolve().parent.parent
I18N_DIR = REPO / "app" / "assets" / "i18n"
OUTPUT_DIR = REPO / "build" / "installer"
ISL_URL = "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages"
# 只放文件名与 Qt 英文语言名不一致的语言，英文用 Default.isl
ISL_NAMES = {
    "en_US": None,
    "zh_CN": "ChineseSimplified",
    "zh_TW": "ChineseTraditional",
    "zh_HK": "ChineseTraditional",
    "pt_BR": "BrazilianPortuguese",
    "ms_MY": "Malaysian",
}


def toIslName(locale: str) -> str | None:
    if locale in ISL_NAMES:
        return ISL_NAMES[locale]
    return QLocale.languageToString(QLocale(locale).language())


def fetchIsl(name: str) -> bytes:
    for url in (f"{ISL_URL}/{name}.isl", f"{ISL_URL}/Unofficial/{name}.isl"):
        try:
            with urlopen(url, timeout=60) as response:
                return response.read()
        except HTTPError as error:
            if error.code != 404:
                raise
    raise SystemExit(f"Inno Setup has no {name}.isl")


def main() -> int:
    locales = sorted(path.name.removeprefix("gd3.").removesuffix(".ts") for path in I18N_DIR.glob("gd3.*.ts"))
    names = sorted({name for locale in locales if (name := toIslName(locale))})
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in names:
        (OUTPUT_DIR / f"{name}.isl").write_bytes(fetchIsl(name))
        lines.append(f'Name: "{name.lower()}"; MessagesFile: "build\\installer\\{name}.isl"')
    (OUTPUT_DIR / "languages.iss").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
