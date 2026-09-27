from http_pack.android import editFields

UI_CLASS = "com.xychr.ghostdownloader.features.github_pack.GitHubUi"

def proxySiteList() -> list:
    from .config import GITHUB_PROXY_SITES
    return list(GITHUB_PROXY_SITES)

async def probeSites() -> dict:
    from .probe import probeProxyLatencies
    return await probeProxyLatencies()
