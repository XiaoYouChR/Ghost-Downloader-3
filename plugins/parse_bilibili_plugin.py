from PySide6.QtCore import Qt

from PySide6.QtGui import QPixmap
import re

from qfluentwidgets import ConfigItem, OptionsConfigItem, OptionsValidator, ConfigValidator, BoolValidator, \
    SettingCardGroup, MessageBoxBase, \
    SubtitleLabel, PlainTextEdit, FluentIcon as FIF

from app.common.config import cfg
from app.common.methods import getFileSizeWithClient, addDownloadTask
from app.common.plugin_base import PluginBase, PluginConfigBase, ComboBoxSettingCard, SwitchSettingCard, PushSettingCard

import httpx

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


class ParseBilibiliPlugin(PluginBase):
    def __init__(self, mainWindow):
        icon = QPixmap(":/plugins/ParseBilibiliPlugin/icon.png")
        super().__init__("哔哩哔哩", "1.0.0", "Bilibili", icon, "哔哩哔哩视频下载扩展，支持批量下载分P视频，需要配置登录cookie才能下载高清视频", mainWindow)

    def loadConfig(self):
        self.config = ParseBilibiliPluginConfig()

        # 添加设置卡片
        settingInterface = self.mainWindow.settingInterface
        self.parseBilibiliGroup = SettingCardGroup("插件: 哔哩哔哩视频下载", settingInterface.scrollWidget)

        self.defaultQualityCard = ComboBoxSettingCard(
            self.config,
            self.config.DefaultQuality,
            FIF.VIDEO,
            "默认清晰度",
            "下载视频时默认的清晰度",
            ["8K", "4K", "1080P60", "1080P+", "1080P", "720P60", "720P", "480P", "360P"],
            self.parseBilibiliGroup
        )

        self.alternativeQualityCard = ComboBoxSettingCard(
            self.config,
            self.config.AlternativeQuality,
            FIF.VIDEO,
            "备选清晰度",
            "下载视频时备选的清晰度",
            ["可以下载的最高画质", "可以下载的最低画质"],
            self.parseBilibiliGroup
        )

        self.parseHDRCard = SwitchSettingCard(
            self.config,
            FIF.VIDEO,
            "HDR",
            "下载 HDR 视频",
            self.config.ParseHDR,
            self.parseBilibiliGroup
        )

        self.parseDolbyCard = SwitchSettingCard(
            self.config,
            FIF.VIDEO,
            "杜比视界",
            "下载杜比视界视频",
            self.config.ParseDolby,
            self.parseBilibiliGroup
        )

        self.userCookieCard = PushSettingCard(
            self.config,
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

    def parseUrl(self, url: str = "", proxy: str = "") -> list[tuple[str, str, int]]:
        """返回视频和音频的下载直链URL, FileName, FileSize 列表"""

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

        userCookie = self.config.UserCookie.value

        if userCookie:
            headers["cookie"] = userCookie

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

        print(videoTitle, pages, pageRange)

        videoInfo = []

        # 遍历选中的分P，提取下载链接
        for pageIndex in pageRange:
            pageIndex = pageIndex - 1
            page = pages[pageIndex]  # 由于页面从 1 开始，数组索引从 0 开始
            for i in self.__getVideoAndAudioLinks(page, videoTitle, pageIndex):
                videoInfo.append(i)
            print(videoInfo)
        # 返回视频和音频的下载链接
        for i in videoInfo:
            addDownloadTask(i[0], i[1], headers=headers, fileSize=i[2])

        return videoInfo

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

    def __getVideoAndAudioLinks(self, page, videoTitle: str, pageIndex: int) -> list[tuple[str, str, int]]:
        """根据页面信息获取音视频资源下载链接"""
        videoQuality = self.config.DefaultQuality.value
        resFiles = []

        cid = page['cid']

        # https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/video/videostream_url.md
        fnval = 16  # DASH
        if self.config.ParseHDR.value:
            fnval |= 64
        if self.config.ParseDolby.value:
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
            if self.config.AlternativeQuality.value == 'max':
                videoQuality = max(pageData['accept_quality'])
            else:
                videoQuality = min(pageData['accept_quality'])

        print("videoQuality", videoQuality)

        for videoOption in pageData['dash']['video']:
            print("ID", videoOption['id'])
            if videoOption['id'] == videoQuality:
                print(True)
                url :str = videoOption['baseUrl']
                resFiles.append((
                    url,  # 视频下载链接
                    f"{videoTitle}_P{pageIndex+1}_{videoOption['height']}P.mp4",  # 文件名
                    getFileSizeWithClient(url, self.client)
                ))
                break
            else:
                continue

        audioOption = pageData['dash']['audio'][0]   # 最高音质
        url = audioOption['baseUrl']
        resFiles.append((
            url,
            f"{videoTitle}_P{pageIndex+1}_{audioOption['id']}P.m4a",  # 文件名
            getFileSizeWithClient(url, self.client)
        ))

        return resFiles

    def load(self):
        # 加载配置
        self.loadConfig()
        # 注册 Url
        self._registerUrl(re.compile(r'https?://(?:www\.)?bilibili\.com/video/(BV[a-zA-Z0-9]+|av\d+)(?:\?p=(\d+(-\d+|\s*,\s*\d+)*))?'))

    def __onUserCookieCardClicked(self):
        item = self.config.UserCookie
        cookie = item.value
        dialog = EditCookieDialog(self.mainWindow, cookie)
        if dialog.exec():
            cookie = dialog.cookieTextEdit.toPlainText()
            self.config.set(item, cookie)
            dialog.deleteLater()

    def unload(self):
        pass

    def uninstall(self):
        pass
