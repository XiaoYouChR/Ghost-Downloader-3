from pathlib import Path

from app.bases.interfaces import FeaturePack
from app.supports.config import DEFAULT_HEADERS
from app.supports.utils import getProxies, toPosixPath
from .task import ExtractStage, InstallStage, InstallTask


class DiskPack(FeaturePack):
    packId = "disk"


async def buildToolInstallTask(
    *,
    packId: str,
    title: str,
    downloadUrl: str,
    fallbackAssetName: str,
    fallbackSize: int,
    installFolder: Path,
    executableNames: list[str],
    headers: dict[str, str] | None = None,
) -> InstallTask:
    from app.services.feature_service import featureService

    downloadPayload = {
        "url": downloadUrl,
        "headers": (headers or DEFAULT_HEADERS).copy(),
        "proxies": getProxies(),
        "path": installFolder,
    }
    downloadTask = await featureService.parse(downloadPayload)
    if not downloadTask.stages:
        raise RuntimeError(f"解析 {fallbackAssetName} 下载链接后未获取到下载阶段")

    downloadStage = downloadTask.stages[0]
    archiveSize = downloadTask.fileSize if downloadTask.fileSize > 0 else fallbackSize
    assetName = downloadTask.title or fallbackAssetName
    archivePath = toPosixPath(installFolder / assetName)

    downloadStage.stageIndex = 1
    downloadStage.outputFile = archivePath

    task = InstallTask(
        title=title,
        url=downloadTask.url,
        packId=packId,
        fileSize=archiveSize,
        path=installFolder,
        usesSlot=False,
        metadata={
            "installFolder": str(installFolder),
            "assetName": assetName,
        },
    )
    extractDir = toPosixPath(installFolder / ".extracting")
    task.addStage(downloadStage)
    task.addStage(ExtractStage(
        stageIndex=2,
        archivePath=archivePath,
        outputFolder=extractDir,
        archiveSize=archiveSize,
    ))
    task.addStage(InstallStage(
        stageIndex=3,
        sourceDir=extractDir,
        installFolder=toPosixPath(installFolder),
        archivePath=archivePath,
        executableNames=executableNames,
    ))
    return task
