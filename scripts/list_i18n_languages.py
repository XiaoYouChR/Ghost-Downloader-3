import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
I18N_DIR = REPO / "app" / "assets" / "i18n"
THRESHOLD = 60
# 新语言按桌面端的完成度三端一起进入仓库，见 docs/adr/0035
SOURCE_PATH = "/app/assets/i18n/gd3.zh_CN.ts"


def fetch(path: str, token: str) -> list[dict]:
    request = Request(f"https://api.crowdin.com/api/v2/{path}", headers={"Authorization": f"Bearer {token}"})
    with urlopen(request, timeout=60) as response:
        return [item["data"] for item in json.load(response)["data"]]


def fetchProgress(projectId: str, token: str) -> list[dict]:
    files = fetch(f"projects/{projectId}/files?limit=500", token)
    fileId = next(file["id"] for file in files if file["path"] == SOURCE_PATH)
    return fetch(f"projects/{projectId}/files/{fileId}/languages/progress?limit=500", token)


def matchLanguages(progress: list[dict]) -> list[str]:
    languages = []
    for item in progress:
        locale = item["language"]["locale"].replace("-", "_")
        if (I18N_DIR / f"gd3.{locale}.ts").exists() or item["translationProgress"] >= THRESHOLD:
            languages.append(item["languageId"])
    return sorted(languages)


def main() -> int:
    progress = fetchProgress(os.environ["CROWDIN_PROJECT_ID"], os.environ["CROWDIN_PERSONAL_TOKEN"])
    print(" ".join(f"-l {language}" for language in matchLanguages(progress)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
