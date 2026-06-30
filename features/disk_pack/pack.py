from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urlparse

from app.models.pack import FeaturePack, TaskParser
from app.models.task import BinaryInstallOptions, Task, TaskOptions
from app.platform.filesystem import toPosixPath
from .task import BinaryInstallStep, ChecksumStep, ExtractStep, InstallStep, InstallTask

ARCHIVE_SUFFIXES = (".zip", ".tar.gz")


def isArchive(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


def assetNameFromUrl(url: str) -> str:
    return PurePosixPath(urlparse(url).path).name


class InstallParser(TaskParser):
    priority = 55

    def match(self, options: TaskOptions) -> bool:
        return isinstance(options, BinaryInstallOptions)

    async def parse(self, options: BinaryInstallOptions) -> Task:
        from app.services.feature_service import featureService

        installFolder = options.outputFolder
        assetName = assetNameFromUrl(options.url)

        download = await featureService.parse(
            TaskOptions(url=options.url, outputFolder=installFolder)
        )
        downloadStep = download.steps[0]

        archive = isArchive(assetName)
        if archive:
            targetPath = toPosixPath(installFolder / assetName)
        else:
            binaryName = options.executableNames[0] if options.executableNames else assetName
            targetPath = toPosixPath(installFolder / binaryName)
        downloadStep.outputFile = targetPath

        task = InstallTask(
            name=options.name or assetName,
            url=options.url,
            packId="disk",
            fileSize=download.fileSize,
            outputFolder=installFolder,
            installFolder=str(installFolder),
        )
        stepIndex = 1
        downloadStep.stepIndex = stepIndex
        task.addStep(downloadStep)
        stepIndex += 1

        if options.sha256Url:
            checksumDownload = await featureService.parse(
                TaskOptions(url=options.sha256Url, outputFolder=installFolder)
            )
            checksumStep = checksumDownload.steps[0]
            sha256Path = toPosixPath(installFolder / assetNameFromUrl(options.sha256Url))
            checksumStep.outputFile = sha256Path
            checksumStep.stepIndex = stepIndex
            task.addStep(checksumStep)
            stepIndex += 1
            task.addStep(ChecksumStep(
                stepIndex=stepIndex, targetFile=targetPath, sha256File=sha256Path,
            ))
            stepIndex += 1

        if archive:
            extractFolder = toPosixPath(installFolder / ".extracting")
            task.addStep(ExtractStep(
                stepIndex=stepIndex,
                archivePath=targetPath,
                outputFolder=extractFolder,
                archiveSize=download.fileSize,
            ))
            stepIndex += 1
            task.addStep(InstallStep(
                stepIndex=stepIndex,
                sourceFolder=extractFolder,
                installFolder=toPosixPath(installFolder),
                archivePath=targetPath,
                executableNames=list(options.executableNames),
            ))
        else:
            task.addStep(BinaryInstallStep(stepIndex=stepIndex, binaryPath=targetPath))

        return task


class DiskPack(FeaturePack):
    packId = "disk"

    def parsers(self):
        return [InstallParser()]
