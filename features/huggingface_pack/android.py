UI_CLASS = "com.xychr.ghostdownloader.features.huggingface_pack.HuggingFaceUi"

def mirrorSiteList() -> list:
    from .config import MIRROR_SITES
    return list(MIRROR_SITES)

def tokenUrl() -> str:
    from .config import TOKEN_URL
    return TOKEN_URL

async def probeSites() -> dict:
    from .config import probeMirrorLatencies
    return await probeMirrorLatencies()
