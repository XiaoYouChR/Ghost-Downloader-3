# 借鉴 https://github.com/monkeyWie/gopeed-extension-bilibili
import hashlib

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
import re

from qfluentwidgets import ConfigItem, OptionsConfigItem, OptionsValidator, ConfigValidator, BoolValidator, \
    SettingCardGroup, FluentIcon as FIF, ComboBoxSettingCard, SwitchSettingCard, PushSettingCard, MessageBoxBase, \
    SubtitleLabel, PlainTextEdit

from app.common.config import Config
from app.common.methods import plugins
from app.common.plugin_base import PluginBase, PluginConfigBase

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
    DefaultQuality = OptionsConfigItem("Download", "DefaultQuality", "360P", OptionsValidator(["8K", "4K", "1080P60", "1080P+", "1080P", "720P60", "720P", "480P", "360P"]))
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
        super().__init__("哔哩哔哩", "1.0.0", "Bilibili", icon, "哔哩哔哩视频下载扩展，支持批量下载分P视频，需要配置登录cookie才能下载高清视频", mainWindow, re.compile(r'https?://(?:www\.)?bilibili\.com/video/(BV[a-zA-Z0-9]+|av\d+)(?:\?p=(\d+(-\d+|\s*,\s*\d+)*))?'))

        self.config = ParseBilibiliPluginConfig()

        # 使用 httpx.Client 来复用连接
        self.client = httpx.Client(
            headers=self._getDefaultHeaders(),  # 设置默认请求头
            cookies=self._getCookies(),  # 设置 cookies
            timeout=30,  # 设置请求超时
            limits=httpx.Limits(max_connections=10)  # 设置最大连接数
        )

    def _getDefaultHeaders(self) -> dict:
        """生成常见的请求头"""
        return {
            "accept-encoding": "deflate, br, gzip",
            "accept-language": "zh-CN,zh;q=0.9",
            "cookie": "down_ip=1",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64",
            "referer": "https://www.bilibili.com/video/BV1454y187Er/",
        }

    def _getCookies(self) -> dict:
        """获取用户 Cookie"""
        userCookie = self.config.UserCookie.value
        if userCookie:
            # 如果有用户 Cookie，将其添加到 cookies 中
            return {"cookie": userCookie}
        return {}

    def parseUrl(self, url: str = "https://www.bilibili.com/video/BV1A4F4egEEF?p=1") -> tuple[tuple[str, str, int]]:
        """返回视频和音频的下载直链URL, FileName, FileSize 列表"""

        match = re.match(r'https?://(?:www\.)?bilibili\.com/video/(BV[a-zA-Z0-9]+|av\d+)(?:\?p=(\d+(-\d+|\s*,\s*\d+)*))?', url)
        if not match:
            raise ValueError("Invalid Bilibili video URL")

        videoId = match.group(1)  # 获取 BV 或 AV 号
        pageParam = match.group(2)  # 获取 P 参数（如果存在）

        # 如果是 AV 号，转换为 BV 号
        if videoId.startswith('av'):
            videoId = self._convertAvToBv(videoId[2:])  # 只需要 AV 号部分，去掉 'av'

        # 获取视频的API接口
        apiUrl = f"https://api.bilibili.com/x/web-interface/view?bvid={videoId}"

        # 发起请求
        response = self.client.get(apiUrl)
        if response.status_code != 200:
            raise ValueError(f"Failed to fetch video data: {response.status_code}")

        # 解析返回的JSON数据
        videoData = response.json()
        if videoData.get('code') != 0:
            raise ValueError(f"Error fetching video info: {videoData.get('message')}")

        # 获取视频标题作为文件名
        videoTitle = videoData['data']['title']

        # 获取所有分P的视频信息
        pages = videoData['data']['pages']

        # 如果没有提供 `p` 参数，下载所有分P视频
        if not pageParam:
            pageRange = range(1, len(pages) + 1)
        else:
            # 如果提供了 `p` 参数，解析为数字区间或列表
            pageRange = self._parsePageParam(pageParam, len(pages))

        videoFiles = []

        # 遍历选中的分P，提取下载链接
        for pageIndex in pageRange:
            page = pages[pageIndex - 1]  # 由于页面从 1 开始，数组索引从 0 开始
            pageQuality = self.config.DefaultQuality.value  # 默认清晰度
            videoFiles.extend(self._getVideoAndAudioLinks(page, videoTitle, pageQuality))

        # 返回视频和音频的下载链接
        return tuple(videoFiles)

    def _convertAvToBv(self, avId: str) -> str:
        """将 AV 号转换为 BV 号"""
        apiUrl = f"https://api.bilibili.com/x/web-interface/view?aid={avId}"
        response = self.client.get(apiUrl)
        if response.status_code != 200:
            raise ValueError(f"Failed to fetch AV data: {response.status_code}")

        videoData = response.json()
        if videoData.get('code') != 0:
            raise ValueError(f"Error fetching AV info: {videoData.get('message')}")

        # 返回转换后的 BV 号
        return videoData['data']['bvid']

    def _parsePageParam(self, pageParam: str, totalPages: int) -> range:
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

    def _getVideoAndAudioLinks(self, page, videoTitle: str, quality: str) -> list:
        """根据页面信息获取音视频资源下载链接"""
        videoFiles = []
        # 提取视频下载链接
        for videoOption in page['dash']['video']:
            if videoOption['quality'] == quality:
                videoFiles.append((
                    videoOption['baseUrl'],  # 视频下载链接
                    f"{videoTitle}_P{page['page']}_{quality}.mp4",  # 文件名
                    videoOption['size']  # 文件大小
                ))

        # 提取音频下载链接
        for audioOption in page['dash']['audio']:
            videoFiles.append((
                audioOption['baseUrl'],  # 音频下载链接
                f"{videoTitle}_P{page['page']}_audio.mp4",  # 文件名
                audioOption['size']  # 文件大小
            ))

        return videoFiles

    def load(self):
        # 添加设置卡片
        settingInterface = self.mainWindow.settingInterface
        self.parseBilibiliGroup = SettingCardGroup("插件: 哔哩哔哩视频下载", settingInterface.scrollWidget)

        self.defaultQualityCard = ComboBoxSettingCard(
            self.config.DefaultQuality,
            FIF.VIDEO,
            "默认清晰度",
            "下载视频时默认的清晰度",
            ["8K", "4K", "1080P60", "1080P+", "1080P", "720P60", "720P", "480P", "360P"],
            self.parseBilibiliGroup
        )

        self.alternativeQualityCard = ComboBoxSettingCard(
            self.config.AlternativeQuality,
            FIF.VIDEO,
            "备选清晰度",
            "下载视频时备选的清晰度",
            ["可以下载的最高画质", "可以下载的最低画质"],
            self.parseBilibiliGroup
        )

        self.parseHDRCard = SwitchSettingCard(
            FIF.VIDEO,
            "HDR",
            "下载 HDR 视频",
            self.config.ParseHDR,
            self.parseBilibiliGroup
        )

        self.parseDolbyCard = SwitchSettingCard(
            FIF.VIDEO,
            "杜比视界",
            "下载杜比视界视频",
            self.config.ParseDolby,
            self.parseBilibiliGroup
        )

        self.userCookieCard = PushSettingCard(
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