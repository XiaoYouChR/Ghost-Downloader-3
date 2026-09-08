"""Android View adapter for M3U8Pack."""


def taskFields(task) -> dict:
    return {"isLive": task.isLive}
