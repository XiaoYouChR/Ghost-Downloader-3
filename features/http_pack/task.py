from dataclasses import field, dataclass

import niquests

from app.bases.interfaces import Worker
from app.bases.models import Task, TaskStage
from app.supports.config import DEFAULT_HEADERS
from app.supports.utils import getProxies
from features.http_pack.const import SpecialFileSize


class HttpTaskStage(TaskStage):
    url: str
    fileSize: int
    headers: dict
    proxies: dict

@dataclass
class HttpTask(Task):
    url: str
    fileSize: int
    headers: dict = field(default_factory=DEFAULT_HEADERS.copy)
    proxies: dict = field(default_factory=getProxies)

@dataclass
class HttpSubworker:
    start: int
    progress: int
    end: int


class HttpWorker(Worker):
    def __init__(self, stage: HttpTaskStage):
        super().__init__(stage)
        self.stage = stage

    async def reassignWorker(self) -> HttpSubworker:
        ...

    async def handleSubworker(self, subworker: HttpSubworker):
        if subworker.end == SpecialFileSize.UNKNOWN:  # 支持断点续传, 但文件大小未知
            ...
        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:  # 不支持断点续传
            ...
        else:  # 正常下载
            while subworker.progress < subworker.end:
                requestHeaders = self.stage.headers.copy()
                requestHeaders["range"] = f"bytes={subworker.progress}-{subworker.end}"

                res = await niquests.aget(self.stage.url, headers=requestHeaders, proxies=self.stage.proxies,
                                          verify=False, allow_redirects=True, stream=True)

                async for chunk in await res.iter_raw(chunk_size=65536):
                    ...

    async def run(self):
        ...
