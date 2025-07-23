from typing import Callable
import curl_cffi


class Worker:
    def __init__(self, start, end, pos=0, parent: 'DownloadTask' = None):
        self.start = start
        self.end = end
        self.pos = pos
        self.chunkSize = 4194304  # 4MB
        self.session = parent.session  # type: curl_cffi.AsyncSession
        self.parent = parent

    @property
    def progress(self):
        return self.pos - self.start

    @property
    def size(self):
        return self.end - self.start + 1

    @property
    def isComplete(self):
        return self.progress >= self.size

    async def download(self):
        if self.isComplete:
            return  # 防止创建空线程
        workingRangeHeaders = self.parent.headers.copy()
        while not self.isComplete:
            try:
                workingRangeHeaders['range'] = f'bytes={self.pos}-{self.end}'

                async with self.session.stream(
                    headers = workingRangeHeaders
                ) as response:
                    response.raise_for_status()

                    if response.status_code != 206:
                        raise RuntimeError(f"服务器拒绝了范围请求, Status Code: {response.status_code}")

                    async for chunk in response.content.aiter_chunks(self.chunkSize):


            except Exception as e:
                ...


class DownloadTask:
    def __init__(self, url):
        self.url = url
        self.headers = {}
        self.preCoroNum = 8
        self.filePath = None
        self.fileName = None
        self.autoSpeedUp: Callable[[DownloadTask, float], ...]
        self.fileSize: int = 0

        self.workers = []
        self.session = None

    def init(self):
        self.session = curl_cffi.AsyncSession(
            max_clients=256,
            trust_env=False,
            allow_redirects=True,
            impersonate='chrome',
            http_version='v3'
        )

