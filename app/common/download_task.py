import re
import urllib
from email.utils import decode_rfc2231
from pathlib import Path
from time import sleep, time
from urllib.parse import urlparse, parse_qs, unquote

import httpx
from PySide6.QtCore import QThread, Signal
from httpx import Client
from loguru import logger

from app.common.config import cfg
try:
    from ..view.main_window import MainWindow
except:
    pass
from app.common.methods import getWindowsProxy, getReadableSize

from qfluentwidgets import PasswordLineEdit, MessageBoxBase, SubtitleLabel, LineEdit, MessageBox

class PasswordBox(MessageBoxBase):
    """ Custom message box """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel('输入账密')
        self.lineEdit = LineEdit()
        self.lineEdit.setPlaceholderText('输入账户名/E-mail地址')
        self.lineEdit.setClearButtonEnabled(True)
        self.pswdLineEdit = PasswordLineEdit()

        self.pswdLineEdit.setPlaceholderText('输入密码')
        self.pswdLineEdit.setClearButtonEnabled(True)

        # 将组件添加到布局中
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.lineEdit)
        self.viewLayout.addWidget(self.pswdLineEdit)

        # 设置对话框的最小宽度
        self.widget.setMinimumWidth(350)


def showMessage():
    w = PasswordBox(MainWindow)
    if w.exec():
        return w.lineEdit.text(), w.pswdLineEdit.text()

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
    try:
        response = httpx.head(url=url, headers=Headers, follow_redirects=False, verify=False,
                              proxy=getWindowsProxy())

        if response.status_code == 400:  # Bad Requests
            # TODO 报错处理
            logger.error("HTTP status code 400, it seems that the url is unavailable")
            return

        while response.status_code == 401: # Unauthorized
            # 获取账密
            account, password = showMessage()
            if not password:
                url.replace("https://", f"https://{account}@")
            elif not account:
                logger.error("No account found")
                continue
            else:
                url.replace("https://", f"https://{account}:{password}@")
            break

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
                                  proxy=getWindowsProxy())  # 再访问一次

        return url

    # TODO 报错处理
    except httpx.ConnectError as err:
        logger.error(f"Cannot connect to the Internet! Error: {err}")
        return
    except ValueError as err:
        logger.error(f"Cannot connect to the Internet! Error: {err}")
        return


class DownloadTask(QThread):
    """作用相当于包工头"""

    refreshLastProgress = Signal(str)  # 用于读取历史记录后刷新进度
    # processChange = Signal(str)  # 目前进度 且因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    workerInfoChange = Signal(list)  # 目前进度 v3.2版本引进了分段式进度条
    taskFinished = Signal()  # 内置信号的不好用

    def __init__(self, url, maxBlockNum: int = 8, filePath=None, fileName=None, parent=None):
        super().__init__(parent)

        # 获取真实URL
        url = getRealUrl(url)

        head = httpx.head(url, headers=Headers, proxy=getWindowsProxy()).headers

        # 获取文件大小, 判断是否可以分块下载
        if "content-length" not in head:
            self.fileSize = 1
            self.ableToParallelDownload = False
        else:
            self.fileSize = int(head["content-length"])
            self.ableToParallelDownload = True

        # 获取文件名
        if not fileName:
            try:
                # 首先，尝试处理 Content-Disposition 中的 filename* (RFC 5987 格式)
                headerValue = head["content-disposition"]
                if 'filename*' in headerValue:
                    match = re.search(r'filename\*\s*=\s*([^;]+)', headerValue, re.IGNORECASE)
                    if match:
                        fileName = match.group(1)
                        fileName = decode_rfc2231(fileName)
                        fileName = urllib.parse.unquote(fileName[2])  # filename* 后的部分是编码信息

                # 如果 filename* 没有成功获取，尝试处理普通的 filename
                if not fileName and 'filename' in headerValue:
                    match = re.search(r'filename\s*=\s*["\']?([^"\';]+)["\']?', headerValue, re.IGNORECASE)
                    if match:
                        fileName = match.group(1)

                # 移除文件名头尾可能存在的引号
                if fileName:
                    fileName = fileName.strip('"\'')
                else:
                    raise KeyError

                logger.debug(f"方法1获取文件名成功, 文件名:{fileName}")
            except (KeyError, IndexError) as e:
                try:
                    logger.info(f"方法1获取文件名失败, KeyError or IndexError:{e}")
                    # 解析 URL
                    # 解析查询字符串
                    # 获取 response-content-disposition 参数
                    # 解码并分割 disposition
                    # 提取文件名
                    fileName = unquote(parse_qs(urlparse(url).query).get('response-content-disposition', [''])[0]).split("filename=")[-1]
                    # 去掉可能存在的引号
                    if fileName.startswith('"') and fileName.endswith('"'):
                        fileName = fileName[1:-1]
                    elif fileName.startswith("'") and fileName.endswith("'"):
                        fileName = fileName[1:-1]

                    if not fileName:
                        raise KeyError

                    logger.debug(f"方法2获取文件名成功, 文件名:{fileName}")

                except (KeyError, IndexError) as e:
                    # 处理没有文件名的情况
                    logger.info(f"方法2获取文件名失败, KeyError or IndexError:{e}")
                    fileName = urlparse(url).path.split('/')[-1]
                    logger.debug(f"方法3获取文件名成功, 文件名:{fileName}")
            except Exception as e:
                # 什么都 Get 不到的情况
                logger.info(f"获取文件名失败, Exception:{e}")
                content_type = head["content-type"].split('/')[-1]
                fileName = f"downloaded_file{int(time())}.{content_type}"
                logger.debug(f"方法4获取文件名成功, 文件名:{fileName}")

        # 获取文件路径
        if not filePath and Path(filePath).is_dir() == False:
            filePath = Path.cwd()
        else:
            filePath = Path(filePath)
            if not filePath.exists():
                filePath.mkdir()

        # 创建空文件
        Path(f"{filePath}/{fileName}").touch()

        self.process = []
        self.url = url
        self.fileName = fileName
        self.filePath = filePath
        self.maxBlockNum = maxBlockNum
        self.workers: list[DownloadWorker] = []

        self.client = httpx.Client(headers=Headers, verify=False,
                                   proxy=getWindowsProxy())

    def __reassignWorker(self):

        # 找到剩余进度最多的线程
        maxRemainder = 0
        maxRemainderWorker: DownloadWorker = None

        for i in self.workers:
            if (i.endPos - i.process) > maxRemainder:  # TODO 其实逻辑有一点问题, 但是影响不大
                # 记录下剩余任务量最大的工作者的进程和结束位置
                maxRemainderWorkerProcess = i.process
                maxRemainderWorkerEnd = i.endPos
                # 更新剩余任务量
                maxRemainder = (maxRemainderWorkerEnd - maxRemainderWorkerProcess)
                # 记录下剩余任务量最大的worker
                maxRemainderWorker = i

        if maxRemainderWorker and maxRemainder > cfg.maxReassignSize.value * 1048576:
            # 平均分配工作量
            baseShare = maxRemainder // 2
            remainder = maxRemainder % 2

            maxRemainderWorker.endPos = maxRemainderWorkerProcess + baseShare + remainder  # 直接修改好像也不会怎么样

            # 安配新的工人
            s_pos = maxRemainderWorkerProcess + baseShare + remainder + 1

            _ = DownloadWorker(s_pos, s_pos, maxRemainderWorkerEnd, self.url, self.filePath,
                               self.fileName, self.client)
            _.workerFinished.connect(self.__reassignWorker)
            _.start()
            self.workers.insert(self.workers.index(maxRemainderWorker) + 1, _)

            logger.info(
                f"Task{self.fileName} 分配新线程成功, 剩余量：{getReadableSize(maxRemainder)}，修改后的EndPos：{maxRemainderWorker.endPos}，新线程：{_}，新线程的StartPos：{s_pos}")

        else:
            logger.info(
                f"Task{self.fileName} 欲分配新线程失败, 剩余量小于最小分块大小, 剩余量：{getReadableSize(maxRemainder)}")

    def clacDivisionalRange(self):
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

    def run(self):
        # TODO 发消息给主线程
        if not self.ableToParallelDownload:
            self.maxBlockNum = 1
        # 读取历史记录
        # 历史记录.ghd文件采用格式示例: ["start": 0, "process": 0, "end": 100, }, {"start": 101, "process": 111, "end": 200}]
        if Path(f"{self.filePath}/{self.fileName}.ghd").exists():
            try:
                with open(f"{self.filePath}/{self.fileName}.ghd", "r", encoding="utf-8") as f:
                    workersInfo = eval(f.read())
                    logger.debug(f"Task:{self.fileName}, history info is: {workersInfo}")
                    for i in workersInfo:
                        self.workers.append(
                            DownloadWorker(i["start"], i["process"], i["end"], self.url, self.filePath,
                                           self.fileName, self.client))

                self.refreshLastProgress.emit(str(sum([i.process for i in self.workers])))  # 要不然速度会错
            # TODO 错误处理
            except:
                for i in range(self.maxBlockNum):
                    stepList = self.clacDivisionalRange()
                    self.workers.append(
                        DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self.url, self.filePath,
                                       self.fileName, self.client))
        else:
            for i in range(self.maxBlockNum):
                stepList = self.clacDivisionalRange()
                self.workers.append(
                    DownloadWorker(stepList[i][0], stepList[i][0], stepList[i][1], self.url, self.filePath,
                                   self.fileName, self.client))

        for i in self.workers:
            logger.debug(f"Task {self.fileName}, starting the thread {i}...")
            i.workerFinished.connect(self.__reassignWorker)
            i.start()

        # fileResolve = Path(f"{self.filePath}/{self.fileName}")
        # 实时统计进度并写入历史记录文件
        while not self.process == self.fileSize:
            with open(f"{self.filePath}/{self.fileName}.ghd", "w", encoding="utf-8") as f:
                info = [{"start": i.startPos, "process": i.process, "end": i.endPos} for i in self.workers]
                f.write(str(info))
                f.flush()

            # self.process = os.path.getsize(fileResolve)
            # self.process = sum([i.process - i.startProcess + 1 for i in self.workers])
            # self.processChange.emit(str(self.process))

            self.process = sum([i.process - i.startPos + 1 for i in self.workers])

            self.workerInfoChange.emit(info)

            # print(self.process, self.fileSize)

            sleep(1)

        # 删除历史记录文件
        try:
            Path(f"{self.filePath}/{self.fileName}.ghd").unlink()

        except Exception as e:
            logger.error(f"Failed to delete the history file, please delete it manually. Err: {e}")

        logger.info(f"Task {self.fileName} finished!")

        self.taskFinished.emit()


class DownloadWorker(QThread):
    """只能出卖劳动力的最底层工作者"""

    workerFinished = Signal()  # 内置的信号不好用

    def __init__(self, start, process, end, url, filePath, fileName, client: Client, parent=None):
        super().__init__(parent)
        self.startPos = start
        self.process = process
        self.endPos = end
        self.url = url
        self.filePath = filePath
        self.fileName = fileName
        self.client = client

    def run(self):
        if self.process < self.endPos:  # 因为可能会创建空线程
            finished = False
            while not finished:
                try:
                    download_headers = {"Range": f"bytes={self.process}-{self.endPos}",
                                        "User-Agent": Headers["User-Agent"]}

                    self.file = open(f"{self.filePath}/{self.fileName}", "rb+")
                    self.file.seek(self.process)

                    with self.client.stream(url=self.url, headers=download_headers, timeout=30, method="GET") as res:
                        for chunk in res.iter_raw(chunk_size=65536):  # iter_content 的单位是字节, 即每64K写一次文件
                            if self.endPos <= self.process:
                                break
                            if chunk:
                                self.file.write(chunk)
                                self.process += 65536

                    if self.process >= self.endPos:
                        self.process = self.endPos

                    try:
                        self.file.close()
                    except:
                        pass

                    finished = True

                except Exception as e:
                    logger.info(f"Task: {self.fileName}, Thread {self} is reconnecting to the server, Error: {e}")

                    try:
                        self.file.close()
                    except:
                        pass

                    sleep(5)

            self.process = self.endPos
            self.workerFinished.emit()
