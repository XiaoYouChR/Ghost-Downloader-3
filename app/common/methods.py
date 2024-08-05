import time
from typing import Union

import requests
from loguru import logger
from PySide6.QtGui import QGuiApplication

from .download_task import urlRe
from .tool_hub import getReadableSize


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
    通过`_url`获取适当线程数，``需发送requests.head请求``

    Params:
        _url: str                   | 链接
        _headers: Union[dict, None] | 请求头
    
    Returns:
        int
    """
    count = 24
    if urlRe.search(_url) is None:
        return count

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
            
    contentLengthUnit = getReadableSize(int(contentLength), is_unit=True)
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
