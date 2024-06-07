import re
from pathlib import Path
from time import time, sleep
from urllib.parse import urlparse

import requests
from PySide6.QtCore import QThread, Signal

from app.common.tool_hub import getWindowsProxy

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
        response = requests.head(url=url, headers=Headers, allow_redirects=False, verify=False,
                                 proxies=getWindowsProxy())

        if response.status_code == 400:  # Bad Requests
            # TODO 报错处理
            print("ERROR!", "HTTP400!Bad Url!\n请尝试更换下载链接!")
            return

        while response.status_code == 302:  # 当302的时候
            rs = response.headers["location"]  # 获取重定向信息
            print(f'Status_Code:302, Headers["Location"] Info: {rs}')
            # 看它返回的是不是完整的URL
            t = urlRe.search(rs)
            if t:  # 是的话直接跳转
                url = rs
            elif not t:  # 不是在前面加上URL
                url = re.findall(r"((?:https?|ftp)://[\s\S]*?)/", url)
                url = url[0] + rs

                print(f"Status_Code:302,Redirect to {url}")

            response = requests.head(url=url, headers=Headers, allow_redirects=False, verify=False,
                                     proxies=getWindowsProxy())  # 再访问一次

        return url

    # TODO 报错处理
    except requests.exceptions.ConnectionError as err:
        print(f"网络连接失败！错误信息：{err}")
        return
    except ValueError as err:
        print(f"网络连接失败！错误信息: {err}")
        return


class DownloadTask(QThread):
    processChange = Signal(str)  # 目前进度 且因为C++ int最大值仅支持到2^31 PyQt又没有Qint类 故只能使用str代替
    taskFinished = Signal()  # 内置信号的不好用

    def __init__(self, url, maxBlockNum: int = 8, filePath=None, fileName=None, parent=None):
        super().__init__(parent)

        # 获取真实URL
        url = getRealUrl(url)

        head = requests.head(url, headers=Headers, proxies=getWindowsProxy()).headers

        # 获取文件大小, 判断是否可以分块下载
        if "content-length" not in head:
            self.fileSize = 0
            self.ableToParallelDownload = False
        else:
            self.fileSize = int(head["content-length"])
            self.ableToParallelDownload = True

        # 获取文件名
        if not fileName:
            try:
                fileName = head["content-disposition"]
                t = re.findall(r"filename=\"([\s\S]*)\"", fileName)
                if t:
                    fileName = t[0]
                else:
                    t = re.findall(r"filename=([\s\S]*);", fileName)
                    fileName = t[0]
                print(f"方法1获取文件名成功, 文件名:{fileName}")
            except KeyError or IndexError as e:
                # 处理没有文件名的情况
                print(f"获取文件名失败, KeyError or IndexError:{e}")
                fileName = urlparse(url).path.split('/')[-1]
                print(f"方法2获取文件名成功, 文件名:{fileName}")
            except Exception as e:
                # 什么都 Get 不到的情况
                print(f"获取文件名失败, Exception:{e}")
                content_type = head["content-type"].split('/')[-1]
                fileName = f"downloaded_file{int(time())}.{content_type}"
                print(f"方法3获取文件名成功, 文件名:{fileName}")

        # 获取文件路径
        if not filePath and Path(filePath).is_dir() == False:
            filePath = Path.cwd()
        else:
            filePath = Path(filePath)
            if not filePath.exists():
                filePath.mkdir()

        # 创建空文件
        Path(f"{filePath}/{fileName}").touch()

        self.process = 0
        self.url = url
        self.fileName = fileName
        self.filePath = filePath
        self.maxBlockNum = maxBlockNum
        self.workers: list[DownloadWorker] = []

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
        # 读取历史记录
        # 历史记录.ghd文件采用格式示例: [{"id": 0, "start": 0, "process": 0, "end": 100, }, {"id": 1, "start": 101, "process": 111, "end": 200}]
        if Path(f"{self.filePath}/{self.fileName}.ghd").exists():
            try:
                with open(f"{self.filePath}/{self.fileName}.ghd", "r", encoding="utf-8") as f:
                    workersInfo = eval(f.read())
                    print(workersInfo)
                    for i in workersInfo:
                        self.workers.append(
                            DownloadWorker(i["id"], i["start"], i["process"], i["end"], self.url, self.filePath,
                                           self.fileName))
            # TODO 错误处理
            except:
                if self.ableToParallelDownload:
                    for i in range(self.maxBlockNum):
                        stepList = self.clacDivisionalRange()
                        self.workers.append(
                            DownloadWorker(i, stepList[i][0], stepList[i][0], stepList[i][1], self.url, self.filePath,
                                           self.fileName))
        else:
            if self.ableToParallelDownload:
                for i in range(self.maxBlockNum):
                    stepList = self.clacDivisionalRange()
                    self.workers.append(
                        DownloadWorker(i, stepList[i][0], stepList[i][0], stepList[i][1], self.url, self.filePath,
                                       self.fileName))

        for i in self.workers:
            print(f"正在启动第{i.id}个线程")
            i.start()

        # 实时统计进度并写入历史记录文件
        while not self.process == self.fileSize:
            with open(f"{self.filePath}/{self.fileName}.ghd", "w", encoding="utf-8") as f:
                f.write(str([{"id": i.id, "start": i.startProcess, "process": i.process, "end": i.end} for i in
                             self.workers]))
                f.flush()

            self.process = sum([i.process - i.startProcess + 1 for i in self.workers])
            self.processChange.emit(str(self.process))

            # print(self.process, self.fileSize)

            sleep(1)

        # 删除历史记录文件
        try:
            Path(f"{self.filePath}/{self.fileName}.ghd").unlink()

        except Exception as e:
            print(f"删除历史记录文件失败, 请手动删除. 错误信息: {e}")

        self.taskFinished.emit()


class DownloadWorker(QThread):
    def __init__(self, id, start, process, end, url, filePath, fileName, parent=None):
        super().__init__(parent)
        self.id = id
        self.startProcess = start
        self.process = process
        self.end = end
        self.url = url
        self.filePath = filePath
        self.fileName = fileName

    def run(self):
        finished = False
        while not finished:
            try:
                download_headers = {"Range": f"bytes={self.process}-{self.end}",
                                    "User-Agent": Headers["User-Agent"]}

                res = requests.get(self.url, headers=download_headers, proxies=getWindowsProxy(), stream=True,
                                   timeout=60)

                self.file = open(f"{self.filePath}/{self.fileName}", "rb+")
                self.file.seek(self.process)
                for chunk in res.iter_content(chunk_size=65536):  # iter_content 的单位是字节, 即每64K写一次文件
                    if chunk:
                        self.file.write(chunk)
                        self.process += 65536

                if self.process >= self.end:
                    self.process = self.end

                self.file.close()
                finished = True

            except Exception as e:
                self.file.close()
                print(f"线程{self.id}正在重连, Error: {e}")
                sleep(5)
