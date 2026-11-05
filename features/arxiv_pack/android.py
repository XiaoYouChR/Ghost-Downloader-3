from http_pack.android import editFields as editHttpFields

UI_CLASS = "com.xychr.ghostdownloader.features.arxiv_pack.ArxivUi"


def editFields(task) -> dict:
    fields = {**editHttpFields(task), "isBibtexEnabled": task.isBibtexEnabled}
    if task.hasSource:
        fields["isSourceEnabled"] = task.isSourceEnabled
    return fields


def draftFields(task) -> dict:
    return {
        "hasSource": task.hasSource,
        "isSourceEnabled": task.isSourceEnabled,
        "isBibtexEnabled": task.isBibtexEnabled,
    }


def setSideFile(task, key: str, isEnabled: bool) -> None:
    task.setOptions({key: bool(isEnabled)})
