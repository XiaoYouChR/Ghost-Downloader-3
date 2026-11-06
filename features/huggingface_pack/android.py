UI_CLASS = "com.xychr.ghostdownloader.features.huggingface_pack.HuggingFaceUi"


def mirrorSiteList() -> list[str]:
    from .config import MIRROR_SITES
    return list(MIRROR_SITES)


def tokenUrl() -> str:
    from .config import TOKEN_URL
    return TOKEN_URL


async def probeSites() -> dict[str, int]:
    from .config import probeMirrorLatencies
    return await probeMirrorLatencies()
