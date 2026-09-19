UI_CLASS = "com.xychr.ghostdownloader.features.huggingface_pack.HuggingFaceUi"

def proxySiteList() -> list:
    from .config import HF_PROXY_SITES
    return list(HF_PROXY_SITES)

def tokenUrl() -> str:
    from .config import TOKEN_URL
    return TOKEN_URL

async def probeSites() -> dict:
    from .config import probeProxyLatencies
    return await probeProxyLatencies()
