from http_pack.android import editFields

UI_CLASS = "com.xychr.ghostdownloader.features.github_pack.GitHubUi"

async def probeSites() -> dict:
    from .config import probeProxyLatencies

    return await probeProxyLatencies()
