UI_CLASS = "com.xychr.ghostdownloader.features.huggingface_pack.HuggingFaceUi"

async def probeSites() -> dict:
    from .config import probeProxyLatencies

    return await probeProxyLatencies()
