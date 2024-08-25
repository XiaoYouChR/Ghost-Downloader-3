import re
import urllib
from email.utils import decode_rfc2231
from pathlib import Path
from time import sleep, time
from urllib.parse import urlparse, parse_qs, unquote

import httpx,aiofiles,asyncio
from PySide6.QtCore import QThread, Signal
from httpx import Client
from loguru import logger

from app.common.config import cfg
from app.common.methods import getProxy, getReadableSize, retry

Headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"}

urlRe = re.compile(r"^" +
                   "((?:https?|ftp)://)" +
                   "(?:\\S+(?::\\S*)?@)?" +
                   "(?:" +
                   "(?:[1-9]\\d?|1\\d\\d|2[01]\\d|22[0-3])" +
                   "(?:\\.(?:1?\\d{1,2}|2[0-4]\\d|25[0-5])){2}" +
                   "(\\.(?:[1-9]\\d?|1\\d\\d|2[0-4]\\d|25[0-4]))" +
                   "|" +
                   "((?:[a-z\\u00a1-\\uffff0-9]-*)*[a-z\\u00a1-\\uffff0-9]+)" +
                   '(?:\\.(?:[a-z\\u00a1-\\uffff0-9]-*)*[a-z\\u00a1-\\uffff0-9]+)*' +
                   "(\\.([a-z\\u00a1-\\uffff]{2,}))" +
                   ")" +
                   "(?::\\d{2,5})?" +
                   "(?:/\\S*)?" +
                   "$", re.IGNORECASE)


def getRealUrl(url: str):
    # try:
        response = httpx.head(url=url, headers=Headers, follow_redirects=False, verify=False,
                              proxy=getProxy())

        if response.status_code == 400:  # Bad Requests
            # TODO 报错处理
            logger.error("HTTP status code 400, it seems that the url is unavailable")
            return

        while response.status_code == 302:  # 当302的时候
            rs = response.headers["location"]  # 获取重定向信息
            logger.info(f'HTTP status code:302, Headers["Location"] is: {rs}')
            # 看它返回的是不是完整的URL
            t = urlRe.search(rs)
            if t:  # 是的话直接跳转
                url = rs
            elif not t:  # 不是在前面加上URL
                url = re.findall(r"((?:https?|ftp)://[\s\S]*?)/", url)
                url = url[0] + rs

                logger.info(f"HTTP status code:302, Redirect to {url}")

            response = httpx.head(url=url, headers=Headers, follow_redirects=False, verify=False,
                                  proxy=getProxy())  # 再访问一次

        return url

    # TODO 报错处理
    # except httpx.ConnectError as err:
    #     logger.error(f"Cannot connect to the Internet! Error: {err}")
    #     return
    # except ValueError as err:
    #     logger.error(f"Cannot connect to the Internet! Error: {err}")
    #     return
    # except httpx.ConnectTimeout as err:
    #     logger.error(f"Cannot connect to the Internet! Error: {err}")
    #     return

class DownloadTask(QThread):
    """作用相当于包工头"""

    taskInited = Signal()  # 线程初始化成功
    # processChange = Signal(str)  # 目前进度 且因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    workerInfoChange = Signal(list)  # 目前进度 v3.2版本引进了分段式进度条
    taskFinished = Signal()  # 内置信号的不好用
    gotWrong = Signal(str)  # 😭 我出问题了

    def __init__(self, url, maxBlockNum: int = 8, filePath=None, fileName=None, parent=None):
        super().__init__(parent)

        self.process = []
        self.url = url
        self.fileName = fileName
        self.filePath = filePath
        self.maxBlockNum = maxBlockNum
        self.workers: list[DownloadWorker] = []
        self.file_manager = aiofiles.open(f"{filePath}/{fileName}",'w+b')
        self.file_lock = asyncio.Lock()#锁

        self.client = httpx.AsyncClient(headers=Headers, verify=False,
                                   proxy=getProxy())

    def reassignWorker(self):

        # 找到剩余进度最多的线程
        maxRemainder = 0
        maxRemainderWorker: DownloadWorker = None

        for i in self.workers:
            if (i.endPos - i.process) > maxRemainder:  # TODO 其实逻辑有一点问题, 但是影响不大 
                maxRemainderWorkerProcess = i.process
                maxRemainderWorkerEnd = i.endPos
                maxRemainder = (maxRemainderWorkerEnd - maxRemainderWorkerProcess)
                maxRemainderWorker = i

        if maxRemainderWorker and maxRemainder > cfg.maxReassignSize.value * 1048576:
            # 平均分配工作量
            baseShare = maxRemainder // 2
            remainder = maxRemainder % 2

            maxRemainderWorker.endPos = maxRemainderWorkerProcess + baseShare + remainder  # 直接修改好像也不会怎么样

            # 安配新的工人
            s_pos = maxRemainderWorkerProcess + baseShare + remainder + 1

            _ = DownloadWorker(s_pos, s_pos, maxRemainderWorkerEnd, self)
            asyncio.create_task(_.run())
            self.workers.insert(self.workers.index(maxRemainderWorker) + 1, _)

            logger.info(
                f"Task{self.fileName} 分配新线程成功, 剩余量：{getReadableSize(maxRemainder)}，修改后的EndPos：{maxRemainderWorker.endPos}，新线程：{_}，新线程的StartPos：{s_pos}")

        else:
            logger.info(
                f"Task{self.fileName} 欲分配新线程失败, 剩余量小于最小分块大小, 剩余量：{getReadableSize(maxRemainder)}")
    
    def clacDivisionalRange(self):
        '''预先分块'''
        step = self.fileSize // self.maxBlockNum  # 每块大小
        arr = list(range(0, self.fileSize, step))

        # 否则线程数可能会不按预期地少一个
        if self.fileSize % self.maxBlockNum == 0:
            arr.append(self.fileSize)

        step_list = []

        for i in range(len(arr) - 1):  #

            s_pos, e_pos = arr[i], arr[i + 1] - 1
            step_list.append([s_pos, e_pos])

        step_list[-1][-1] = self.fileSize - 1  # 修正

        return step_list


    @retry(3, 0.1)
    def run(self):
        try:
            asyncio.run(self.main())
        except asyncio.exceptions.CancelledError:
            logger.info('任务被取消/暂停')
        

    async def main(self):
        self.task = asyncio.current_task()
        try:
            # 初始化信息
            # 获取真实URL
            self.url = getRealUrl(self.url)

            head = httpx.head(self.url, headers=Headers, proxy=getProxy()).headers

        except Exception as e: # 重试也没用

            self.gotWrong.emit(str(e))

        # 获取文件大小, 判断是否可以分块下载
        if "content-length" not in head:
            self.fileSize = 1
            self.ableToParallelDownload = False
        else:
            self.fileSize = int(head["content-length"])
            self.ableToParallelDownload = True

        # 获取文件名
        if not self.fileName:
            try:
                # 首先，尝试处理 Content-Disposition 中的 self.fileName* (RFC 5987 格式)
                headerValue = head["content-disposition"]
                if 'fileName*' in headerValue:
                    match = re.search(r'filename\*\s*=\s*([^;]+)', headerValue, re.IGNORECASE)
                    if match:
                        self.fileName = match.group(1)
                        self.fileName = decode_rfc2231(self.fileName)
                        self.fileName = urllib.parse.unquote(self.fileName[2])  # self.fileName* 后的部分是编码信息

                # 如果 self.fileName* 没有成功获取，尝试处理普通的 self.fileName
                if not self.fileName and 'filename' in headerValue:
                    match = re.search(r'filename\s*=\s*["\']?([^"\';]+)["\']?', headerValue, re.IGNORECASE)
                    if match:
                        self.fileName = match.group(1)

                # 移除文件名头尾可能存在的引号
                if self.fileName:
                    self.fileName = self.fileName.strip('"\'')
                else:
                    raise KeyError

                logger.debug(f"方法1获取文件名成功, 文件名:{self.fileName}")
            except (KeyError, IndexError) as e:
                try:
                    logger.info(f"方法1获取文件名失败, KeyError or IndexError:{e}")
                    # 解析 URL
                    # 解析查询字符串
                    # 获取 response-content-disposition 参数
                    # 解码并分割 disposition
                    # 提取文件名
                    self.fileName = unquote(parse_qs(urlparse(self.url).query).get('response-content-disposition', [''])[0]).split("filename=")[-1]
                    # 去掉可能存在的引号
                    if self.fileName.startswith('"') and self.fileName.endswith('"'):
                        self.fileName = self.fileName[1:-1]
                    elif self.fileName.startswith("'") and self.fileName.endswith("'"):
                        self.fileName = self.fileName[1:-1]

                    if not self.fileName:
                        raise KeyError

                    logger.debug(f"方法2获取文件名成功, 文件名:{self.fileName}")

                except (KeyError, IndexError) as e:
                    # 处理没有文件名的情况
                    logger.info(f"方法2获取文件名失败, KeyError or IndexError:{e}")
                    self.fileName = urlparse(self.url).path.split('/')[-1]
                    logger.debug(f"方法3获取文件名成功, 文件名:{self.fileName}")
            except Exception as e:
                # 什么都 Get 不到的情况
                logger.info(f"获取文件名失败, Exception:{e}")
                content_type = head["content-type"].split('/')[-1]
                self.fileName = f"downloaded_file{int(time())}.{content_type}"
                logger.debug(f"方法4获取文件名成功, 文件名:{self.fileName}")

        # 获取文件路径
        if not self.filePath and Path(self.filePath).is_dir() == False:
            self.filePath = Path.cwd()
        else:
            self.filePath = Path(self.filePath)
            if not self.filePath.exists():
                self.filePath.mkdir()

        self.taskInited.emit()
        
        # TODO 发消息给主线程
        if not self.ableToParallelDownload:
            self.maxBlockNum = 1
        # 读取历史记录
        # 历史记录.ghd文件采用格式示例: ["start": 0, "process": 0, "end": 100, }, {"start": 101, "process": 111, "end": 200}]
        async with self.file_manager as self.file:

            if Path(f"{self.filePath}/{self.fileName}.ghd").exists():
                try:
                    with open(f"{self.filePath}/{self.fileName}.ghd", "r", encoding="utf-8") as f:
                        workersInfo = eval(f.read())
                        logger.debug(f"Task:{self.fileName}, history info is: {workersInfo}")
                        for i in workersInfo:
                            self.workers.append(
                                DownloadWorker(i["start"], i["process"], i["end"], self))

                    #self.refreshLastProgress.emit(str(sum([i.process - i.startPos for i in self.workers])))  # 要不然速度会错
                # TODO 错误处理
                except:
                    stepList = self.clacDivisionalRange()
                    for i in range(self.maxBlockNum):
                        self.workers.append(
                            DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self))
            else:
                stepList = self.clacDivisionalRange()
                for i in range(self.maxBlockNum):
                    self.workers.append(
                        DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self))

            for i in self.workers:
                #logger.debug(f"Task {self.fileName}, starting the thread {i}...")
                asyncio.create_task(i.run())

            # fileResolve = Path(f"{self.filePath}/{self.fileName}")
            # 实时统计进度并写入历史记录文件
            self.process = sum([i.process - i.startPos + 1 for i in self.workers])
            while not self.process == self.fileSize:
                with open(f"{self.filePath}/{self.fileName}.ghd", "w", encoding="utf-8") as f:
                    info = [{"start": i.startPos, "process": i.process, "end": i.endPos} for i in self.workers]
                    f.write(str(info))
                    f.flush()

                    # self.process = os.path.getsize(fileResolve)
                    # self.process = sum([i.process - i.startProcess + 1 for i in self.workers])
                    # self.processChange.emit(str(self.process))


                    self.workerInfoChange.emit(info)

                    # print(self.process, self.fileSize)

                    await asyncio.sleep(1)
            info = [{"start": i.startPos, "process": i.process, "end": i.endPos} for i in self.workers]#完成后额外刷新一次
            #等待所有任务完成,不加会报错
            for i in self.workers:
                await i.task
            await self.file.close()
            

        # 删除历史记录文件
        try:
            Path(f"{self.filePath}/{self.fileName}.ghd").unlink()

        except Exception as e:
            logger.error(f"Failed to delete the history file, please delete it manually. Err: {e}")

        logger.info(f"Task {self.fileName} finished!")
        self.workerInfoChange.emit(info)
        self.taskFinished.emit()


class DownloadWorker:
    """只能出卖劳动力的最底层工作者"""


    def __init__(self, start, process, end, mission:DownloadTask):
        self.startPos = start
        self.process = process
        self.endPos = end
        self.mission = mission

    async def run(self):
        mission = self.mission
        self.task = asyncio.current_task()
        if self.process < self.endPos:  # 因为可能会创建空线程
            finished = False
            while not finished:
                try:
                    if mission.ableToParallelDownload:
                        download_headers = {"Range": f"bytes={self.process}-{mission.fileSize}",
                                        "User-Agent": Headers["User-Agent"]}
                    else:
                        download_headers = {"User-Agent": Headers["User-Agent"]}

                    async with mission.client.stream(url=mission.url, headers=download_headers, timeout=30, method="GET") as res:
                        async for chunk in res.aiter_raw(chunk_size=65536):  # iter_content 的单位是字节, 即每64K写一次文件
                            if self.process + 65536 < self.endPos:
                                async with mission.file_lock:
                                    await mission.file.seek(self.process)
                                    await mission.file.write(chunk)
                                self.process += 65536
                                mission.process += 65536
                            else:
                                chunk = chunk[: self.endPos - self.process]
                                len_chunk = self.endPos - self.process
                                async with mission.file_lock:
                                    await mission.file.seek(self.process)
                                    await mission.file.write(chunk)
                                    if (i := mission.workers.index(self) + 1) != len(mission.workers) and mission.workers[i].process > self.process + len_chunk:
                                        i = await mission.file.read(self.process + len_chunk - self.endPos)#
                                        if i != chunk[self.endPos - self.process:]:
                                            logger.error('校验失败')
                                        else:
                                            logger.info(f'{self.startPos}校验成功')
                                    else:
                                        logger.debug('跳过校验')
                                mission.process += len_chunk
                                self.process = self.endPos
                                finished = True
                                break

                except Exception as e:
                    logger.info(f"Task: {mission.fileName}, Thread {self} is reconnecting to the server, Error: {e}")

                    await asyncio.sleep(5)

            self.process = self.endPos
            mission.reassignWorker()
