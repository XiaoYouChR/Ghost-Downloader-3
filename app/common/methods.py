import time
import requests
from typing import Union
from loguru import logger
from PySide6.QtGui import QGuiApplication
from .download_task import urlRe


url = "https://www.pymili-blog.icu/static/MyFlowingFireflyWife/setup/beta-v0.3/MyFlowingFireflyWife-beta-v0.3-win11-pyinstaller.zip"
def getResponseTime(_url: str, _headers: Union[dict, None] = None) -> float:
    """
    通过`requests.head`请求，获取链接响应时间。``（保留一位小数）``

    Params:
        _url: str                   | 请求地址    
        _headers: Union[dict, None] | 请求头
    
    Returns:
        float
    """
    if urlRe.search(_url) is None:
        return 0.0
    requestStart = time.time()
    responseTime = None
    with requests.head(url=_url, headers=_headers, timeout=3) as response:
        requestStop = time.time()
        if response.status_code == 200: 
            responseTime = response.headers.get("Server-Response-Time")
            # print(response.headers.get("content-length"))

    if not responseTime:
        responseTime = requestStop - requestStart
    return round(responseTime, 1)


def estimateThreadCount(_url: str, _headers: Union[dict, None] = None) -> int:
    """
    通过
    """
    count = 24
    if urlRe.search(_url) is None:
        return count

    def unit(_bytes: int) -> str:
        """根据字节数返回适当的单位"""
        if _bytes < 1024:
            return "B"
        elif _bytes < 1024**2:
            return "KB"
        elif _bytes < 1024**3:
            return "MB"
        elif _bytes < 1024**4:
            return "GB"
        else:
            return "TB"
    try:
        responseTime = getResponseTime(_url, _headers)
        with requests.head(url=_url, headers=_headers) as response:
            if response.status_code == 200:
                contentLength = response.headers.get("content-length")
                if not contentLength:
                    return count
    except Exception as e:
        logger.warning(e)
        return count
            
    contentLengthUnit = unit(int(contentLength))
    # 延迟高，且文件大
    if responseTime > 1.0 and contentLengthUnit == "GB":
        count = 16
    # 延迟低，但文件小
    if responseTime <= 0.5 and contentLengthUnit in ["KB", "MB"]:
        count = 8
    return count


def getSystemPasteboardContent() -> str:
    """获取系统粘贴板内容"""
    clipboard = QGuiApplication.clipboard()  # 获取剪贴板对象
    return clipboard.text()  # 获取剪贴板中的文本
