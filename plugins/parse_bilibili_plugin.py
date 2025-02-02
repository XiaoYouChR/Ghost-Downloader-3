from pathlib import Path

from PySide6.QtCore import Qt, QObject

from PySide6.QtGui import QPixmap
import re

from loguru import logger
from qfluentwidgets import ConfigItem, OptionsConfigItem, OptionsValidator, ConfigValidator, BoolValidator, \
    SettingCardGroup, MessageBoxBase, \
    SubtitleLabel, PlainTextEdit, FluentIcon as FIF

from app.common.config import cfg, registerContentsByPlugins
from app.common.download_task import DownloadTask
from app.common.methods import getFileSizeWithClient, addDownloadTask, getProxy
from app.common.plugin_base import PluginBase, PluginConfigBase, ComboBoxSettingCard, SwitchSettingCard, PushSettingCard

import httpx

from app.common.task_base import TaskManagerBase


class EditCookieDialog(MessageBoxBase):
    def __init__(self, parent=None, initialCookie=None):
        super().__init__(parent=parent)
        self.setClosableOnMaskClicked(True)

        self.widget.setFixedSize(400, 500)

        self.titleLabel = SubtitleLabel("编辑 Cookie", self.widget)
        self.viewLayout.addWidget(self.titleLabel)

        self.cookieTextEdit = PlainTextEdit(self.widget)
        self.cookieTextEdit.setPlaceholderText('请在此输入用户 Cookie.')
        self.cookieTextEdit.setPlainText(initialCookie)
        self.viewLayout.addWidget(self.cookieTextEdit)
        

class CookieValidator(ConfigValidator):
    def validate(self, value) -> bool:
        if type(value) == str:
            return True
        return False

    def correct(self, value) -> str:
        return value if self.validate(value) else ""


class ParseBilibiliPluginConfig(PluginConfigBase):
    DefaultQuality = OptionsConfigItem("Download", "DefaultQuality", 16, OptionsValidator([127, 120, 116, 112, 80, 74, 64, 32, 16]))
    AlternativeQuality = OptionsConfigItem("Download", "AlternativeQuality", "max", OptionsValidator(["max", "min"]))
    ParseHDR = ConfigItem("Download", "ParseHDR", False, BoolValidator())
    ParseDolby = ConfigItem("Download", "ParseDolby", False, BoolValidator())
    UserCookie = ConfigItem("Download", "UserCookie", "", CookieValidator())

    def __init__(self):
        pluginName = "parse_bilibili_plugin"
        super().__init__(pluginName)

config = ParseBilibiliPluginConfig()


class ParseBilibiliDownloadManager(TaskManagerBase):
    def __init__(self, url, headers, preBlockNum: int, filePath: str, fileName: str = None,
                 fileSize: int = -1, parent=None):
        QObject.__init__(self, parent=parent)

        self.fileSize = fileSize
        self.url = url
        self.fileName = fileName
        self.filePath = filePath
        self.preBlockNum = preBlockNum  # 假设默认值为0

        self.tasks:list[DownloadTask] = []

    def __parsePageParam(self, pageParam: str, totalPages: int) -> list:
        """解析 P 参数，支持单个、区间和逗号分隔的多个 P"""
        pageRange = []
        if '-' in pageParam:
            # 区间形式 p=1-7
            start, end = map(int, pageParam.split('-'))
            pageRange = range(start, end + 1)
        elif ',' in pageParam:
            # 多个 P 形式 p=1,3,5
            pageRange = list(map(int, pageParam.split(',')))
        else:
            # 单个 P 形式 p=1
            pageRange = [int(pageParam)]

        # 确保 P 参数在有效范围内
        pageRange = [p for p in pageRange if 1 <= p <= totalPages]

        return pageRange

    def start(self):
        match = re.match(r'https?://(?:www\.)?bilibili\.com/video/(BV[a-zA-Z0-9]+|av\d+)(?:\?p=(\d+(-\d+|\s*,\s*\d+)*))?', self.url)
        if not match:
            self.taskGotWrong.emit("Invalid Bilibili video URL")

        # 反爬虫
        headers = {
            "accept-encoding": "deflate, br, gzip",
            "accept-language": "zh-CN,zh;q=0.9",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64",
            "referer": self.url,
        }

        userCookie = config.UserCookie.value

        if userCookie:
            headers["cookie"] = userCookie

        # 使用 httpx.Client 来复用连接
        self.client = httpx.Client(
            headers=headers,  # 设置默认请求头
            timeout=60,  # 设置请求超时
            limits=httpx.Limits(max_connections=256),  # 设置最大连接数
            proxy=getProxy(),
            follow_redirects=True
        )

        self.videoId = match.group(1)  # 获取 BV 或 AV 号
        pageParam = match.group(2)  # 获取 P 参数（如果存在）
        taskInfo = []
        self.fileSize = 0

        # 获取视频的API接口
        if self.videoId.startswith('av'):
            apiUrl = f"https://api.bilibili.com/x/web-interface/view?avid={self.videoId[2:]}"  # 去除 av 前缀
        else:
            apiUrl = f"https://api.bilibili.com/x/web-interface/view?bvid={self.videoId}"

        print(apiUrl)

        # 发起请求
        response = self.client.get(apiUrl)
        response.raise_for_status()

        # 解析返回的JSON数据
        videoData = response.json()

        if not self.fileName:
            # 获取视频标题作为文件名
            videoTitle = videoData['data']['title']
        else:
            videoTitle = self.fileName

        # 获取所有分P的视频信息
        pages = videoData['data']['pages']

        # 如果没有提供 `p` 参数，下载所有分P视频
        if not pageParam:
            pageRange = range(1, len(pages) + 1)
        else:
            # 如果提供了 `p` 参数，解析为数字区间或列表
            pageRange = self.__parsePageParam(pageParam, len(pages))

        print(videoTitle, pageRange)

        # 遍历选中的分P，提取下载链接
        for pageIndex in pageRange:
            pageIndex = pageIndex - 1
            page = pages[pageIndex]  # 由于页面从 1 开始，数组索引从 0 开始

            # 根据页面信息获取音视频资源下载链接
            videoQuality = config.DefaultQuality.value

            cid = page['cid']

            # https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/video/videostream_url.md
            fnval = 16  # DASH
            if config.ParseHDR.value:
                fnval |= 64
            if config.ParseDolby.value:
                fnval |= 256
                fnval |= 512
            if videoQuality == 128:    # 请求 8K
                fnval |= 1024
            if videoQuality == 120:    # 请求 4K
                fnval |= 128

            print(cid, fnval)

            if self.videoId.startswith('av'):
                pageUrl = f"https://api.bilibili.com/x/player/wbi/playurl?avid={self.videoId[2:]}&cid={cid}&fnval={fnval}"
            else:
                pageUrl = f"https://api.bilibili.com/x/player/wbi/playurl?bvid={self.videoId}&cid={cid}&fnval={fnval}"

            print(pageUrl)

            response = self.client.get(pageUrl)
            response.raise_for_status()

            pageData = response.json()['data']

            print(pageData)

            print(pageData['accept_quality'])

            if not videoQuality in pageData['accept_quality']:
                if config.AlternativeQuality.value == 'max':
                    videoQuality = max(pageData['accept_quality'])
                else:
                    videoQuality = min(pageData['accept_quality'])

            print("videoQuality", videoQuality)

            for videoOption in pageData['dash']['video']:
                print("ID", videoOption['id'])
                if videoOption['id'] == videoQuality:
                    print(True)
                    url :str = videoOption['baseUrl']
                    fileSize = getFileSizeWithClient(url, self.client)
                    self.fileSize += fileSize
                    taskInfo.append((
                        url,  # 视频下载链接
                        f"{videoTitle}_P{pageIndex+1}_{videoOption['height']}P.mp4",  # 文件名
                        fileSize                        
                    ))
                    break
                else:
                    continue

            audioOption = pageData['dash']['audio'][0]   # 最高音质
            url = audioOption['baseUrl']
            fileSize = getFileSizeWithClient(url, self.client)
            self.fileSize += fileSize
            taskInfo.append((
                url,
                f"{videoTitle}_P{pageIndex+1}_{audioOption['id']}P.m4a",  # 文件名
                fileSize
            ))

        autoSpeedUp = cfg.autoSpeedUp.value

        for task in taskInfo:
            _ = DownloadTask(task[0], headers, self.preBlockNum, self.filePath, task[1], autoSpeedUp, task[2], self)
            _.start()
            self.tasks.append(_)

        self.taskInited.emit(True)  # 提醒 TaskCard 更新界面

    def stop(self):
        for task in self.tasks:
            task.stop()
            task.wait()
            task.deleteLater()
            
    def cancel(self, completely: bool=False):
        self.stop()
        if completely:  # 删除文件
            for i in self.tasks:
                try:
                    Path(f"{i.filePath}/{i.fileName}").unlink()
                    Path(f"{i.filePath}/{i.fileName}.ghd").unlink()
                    logger.info(f"self:{i.fileName}, delete file successfully!")

                except FileNotFoundError:
                    pass

                except Exception as e:
                    raise e


class ParseBilibiliPlugin(PluginBase):
    def __init__(self, mainWindow):
        icon = QPixmap(":/plugins/parse_bilibili_plugin/icon.png")
        super().__init__("哔哩哔哩", "1.0.0", "Bilibili", icon, "哔哩哔哩视频下载扩展，支持批量下载分 P 视频，需要配置登录 Cookie 才能下载高清视频", mainWindow)

    def loadConfig(self):
        # 添加设置卡片
        settingInterface = self.mainWindow.settingInterface
        self.parseBilibiliGroup = SettingCardGroup("插件: 哔哩哔哩视频下载", settingInterface.scrollWidget)

        self.defaultQualityCard = ComboBoxSettingCard(
            config,
            config.DefaultQuality,
            FIF.VIDEO,
            "默认清晰度",
            "下载视频时默认的清晰度",
            ["8K", "4K", "1080P60", "1080P+", "1080P", "720P60", "720P", "480P", "360P"],
            self.parseBilibiliGroup
        )

        self.alternativeQualityCard = ComboBoxSettingCard(
            config,
            config.AlternativeQuality,
            FIF.VIDEO,
            "备选清晰度",
            "下载视频时备选的清晰度",
            ["可以下载的最高画质", "可以下载的最低画质"],
            self.parseBilibiliGroup
        )

        self.parseHDRCard = SwitchSettingCard(
            config,
            FIF.VIDEO,
            "HDR",
            "下载 HDR 视频",
            config.ParseHDR,
            self.parseBilibiliGroup
        )

        self.parseDolbyCard = SwitchSettingCard(
            config,
            FIF.VIDEO,
            "杜比视界",
            "下载杜比视界视频",
            config.ParseDolby,
            self.parseBilibiliGroup
        )

        self.userCookieCard = PushSettingCard(
            config,
            "设置用户 Cookie",
            FIF.BROOM,
            "用户 Cookie",
            "用于下载高清视频时获取下载链接",
            self.parseBilibiliGroup
        )
        self.userCookieCard.clicked.connect(self.__onUserCookieCardClicked)

        self.parseBilibiliGroup.addSettingCard(self.defaultQualityCard)
        self.parseBilibiliGroup.addSettingCard(self.alternativeQualityCard)
        self.parseBilibiliGroup.addSettingCard(self.parseHDRCard)
        self.parseBilibiliGroup.addSettingCard(self.parseDolbyCard)
        self.parseBilibiliGroup.addSettingCard(self.userCookieCard)

        settingInterface.expandLayout.addWidget(self.parseBilibiliGroup)

    def parseUrl(self, url: str, headers:dict) -> tuple[str, str, int]:
        """返回视频和音频的下载 视频URL, 视频Title, 总FileSize"""

        match = re.match(r'https?://(?:www\.)?bilibili\.com/video/(BV[a-zA-Z0-9]+|av\d+)(?:\?p=(\d+(-\d+|\s*,\s*\d+)*))?', url)
        if not match:
            raise ValueError("Invalid Bilibili video URL")

        # 反爬虫
        headers = {
            "accept-encoding": "deflate, br, gzip",
            "accept-language": "zh-CN,zh;q=0.9",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64",
            "referer": url,
        }

        userCookie = config.UserCookie.value

        if userCookie:
            headers["cookie"] = userCookie

        proxy = getProxy()

        # 使用 httpx.Client 来复用连接
        self.client = httpx.Client(
            headers=headers,  # 设置默认请求头
            timeout=60,  # 设置请求超时
            limits=httpx.Limits(max_connections=256),  # 设置最大连接数
            proxy=proxy,
            follow_redirects=True
        )

        self.videoId = match.group(1)  # 获取 BV 或 AV 号
        pageParam = match.group(2)  # 获取 P 参数（如果存在）
        self.fileSize = 0

        # 获取视频的API接口
        if self.videoId.startswith('av'):
            apiUrl = f"https://api.bilibili.com/x/web-interface/view?avid={self.videoId[2:]}"  # 去除 av 前缀
        else:
            apiUrl = f"https://api.bilibili.com/x/web-interface/view?bvid={self.videoId}"

        print(apiUrl)

        # 发起请求
        response = self.client.get(apiUrl)
        response.raise_for_status()

        # 解析返回的JSON数据
        videoData = response.json()

        # 获取视频标题作为文件名
        videoTitle = videoData['data']['title']

        # 获取所有分P的视频信息
        pages = videoData['data']['pages']

        # 如果没有提供 `p` 参数，下载所有分P视频
        if not pageParam:
            pageRange = range(1, len(pages) + 1)
        else:
            # 如果提供了 `p` 参数，解析为数字区间或列表
            pageRange = self.__parsePageParam(pageParam, len(pages))

        print(videoTitle, pageRange)
        
        # 遍历选中的分P，提取下载链接
        for pageIndex in pageRange:
            pageIndex = pageIndex - 1
            page = pages[pageIndex]  # 由于页面从 1 开始，数组索引从 0 开始

            # 根据页面信息获取音视频资源下载链接
            videoQuality = config.DefaultQuality.value

            cid = page['cid']

            # https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/video/videostream_url.md
            fnval = 16  # DASH
            if config.ParseHDR.value:
                fnval |= 64
            if config.ParseDolby.value:
                fnval |= 256
                fnval |= 512
            if videoQuality == 128:    # 请求 8K
                fnval |= 1024
            if videoQuality == 120:    # 请求 4K
                fnval |= 128

            print(cid, fnval)

            if self.videoId.startswith('av'):
                pageUrl = f"https://api.bilibili.com/x/player/wbi/playurl?avid={self.videoId[2:]}&cid={cid}&fnval={fnval}"
            else:
                pageUrl = f"https://api.bilibili.com/x/player/wbi/playurl?bvid={self.videoId}&cid={cid}&fnval={fnval}"

            print(pageUrl)

            response = self.client.get(pageUrl)
            response.raise_for_status()

            pageData = response.json()['data']

            print(pageData)

            print(pageData['accept_quality'])

            if not videoQuality in pageData['accept_quality']:
                if config.AlternativeQuality.value == 'max':
                    videoQuality = max(pageData['accept_quality'])
                else:
                    videoQuality = min(pageData['accept_quality'])

            print("videoQuality", videoQuality)

            for videoOption in pageData['dash']['video']:
                print("ID", videoOption['id'])
                if videoOption['id'] == videoQuality:
                    print(True)
                    self.fileSize += getFileSizeWithClient(videoOption['baseUrl'] , self.client)
                    break
                else:
                    continue

            audioOption = pageData['dash']['audio'][0]   # 最高音质
            self.fileSize += getFileSizeWithClient(audioOption['baseUrl'] , self.client)

        return url, videoTitle, self.fileSize

    # def __convertAvToBv(self, avId: str) -> str:
    #     """将 AV 号转换为 BV 号"""
    #     apiUrl = f"https://api.bilibili.com/x/web-interface/view?aid={avId}"
    #     response = self.client.get(apiUrl)
    #     response.raise_for_status()
    #
    #     videoData = response.json()
    #     if videoData.get('code') != 0:
    #         raise ValueError(f"Error fetching AV info: {videoData.get('message')}")
    #
    #     # 返回转换后的 BV 号
    #     return videoData['data']['bvid']

    def __parsePageParam(self, pageParam: str, totalPages: int) -> list:
        """解析 P 参数，支持单个、区间和逗号分隔的多个 P"""
        pageRange = []
        if '-' in pageParam:
            # 区间形式 p=1-7
            start, end = map(int, pageParam.split('-'))
            pageRange = range(start, end + 1)
        elif ',' in pageParam:
            # 多个 P 形式 p=1,3,5
            pageRange = list(map(int, pageParam.split(',')))
        else:
            # 单个 P 形式 p=1
            pageRange = [int(pageParam)]

        # 确保 P 参数在有效范围内
        pageRange = [p for p in pageRange if 1 <= p <= totalPages]

        return pageRange

    def load(self):
        # 加载配置
        self.loadConfig()
        # 注册 Url, 键名为 self, 值为 [正则表达式, 插件的parseUrl, 插件的TaskManagerBaseCls]
        registerContentsByPlugins[self] = [re.compile(r'https?://(?:www\.)?bilibili\.com/video/(BV[a-zA-Z0-9]+|av\d+)(?:\?p=(\d+(-\d+|\s*,\s*\d+)*))?'), self.parseUrl, ParseBilibiliDownloadManager]

    def __onUserCookieCardClicked(self):
        item = config.UserCookie
        cookie = item.value
        dialog = EditCookieDialog(self.mainWindow, cookie)
        if dialog.exec():
            cookie = dialog.cookieTextEdit.toPlainText()
            config.set(item, cookie)
            dialog.deleteLater()

    def unload(self):
        # 注销链接
        registerContentsByPlugins.pop(self)

    def uninstall(self):
        pass
