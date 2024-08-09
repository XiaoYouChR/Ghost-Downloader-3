import os
import re
import time
from typing import Union
from urllib.parse import urlparse

import requests
from loguru import logger


class UrlUtils:
    """
    链接工具类
    """
    urlRe = re.compile(
        r"^" +
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
        "$", re.IGNORECASE
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) " \
            "Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"
    }

    @staticmethod
    def responseTime(_url: str, _headers: Union[dict, None] = None) -> float:
        """
        通过`requests.head`请求，获取链接响应时间。
        :param _url: 请求地址
        :param _headers: 请求头
        :return: float
        """
        result = UrlUtils.urlRe.search(_url)
        if not result:
            logger.error(f"链接地址不合法: {_url}")
            return 0
        
        requestStart = time.time()
        responseTime = None
        with requests.head(url=_url, headers=_headers, timeout=3) as response:
            requestStop = time.time()
            if response.status_code == 200: 
                responseTime = response.headers.get("Server-Response-Time")
                # print(response.headers.get("content-length"))

        if not responseTime:
            responseTime = requestStop - requestStart
        return responseTime
    
    @staticmethod
    def byUrlGetFileName(_url: str, proxies: Union[dict, None] = None) -> str:
        """
        获取文件名
        :param _url: 链接地址
        :return: str
        """
        if not UrlUtils.urlRe.search(_url):
            logger.error(f"链接地址不合法: {_url}，将自动生成文件名")
            return "null"
        result = os.path.split(_url)[0]
        with requests.head(_url, headers=UrlUtils.headers, proxies=proxies) as response:
            try:
                _findall = re.findall(
                    r"filename=\"([\s\S]*)\"",
                    response.headers.get("content-disposition")
                )
                if _findall:
                    result = _findall[0]
                else:
                    _findall = re.findall(r"filename=([\s\S]*);", result)
                    result = _findall[0]
                logger.debug(f"方法1获取文件名成功, 文件名:{result}")
            except KeyError or IndexError as e:
                # 处理没有文件名的情况
                logger.info(f"获取文件名失败, KeyError or IndexError:{e}")
                result = urlparse(_url).path.split('/')[-1]
                logger.debug(f"方法2获取文件名成功, 文件名:{result}")
            except Exception as e:
                # 什么都 Get 不到的情况
                if re.search(r'/(.+)\.\w+$', _url) is None:
                    logger.info(f"获取文件名失败, Exception:{e}")
                    content_type = response.headers.get("content-type").split('/')[-1]
                    result = f"downloaded_file{int(time.time())}.{content_type}"
                    logger.debug(f"方法3获取文件名成功, 文件名:{result}")
                    return result
                result = os.path.split(_url)[-1]
                logger.debug(f"方法4获取文件名成功, 文件名:{result}")

        return result
    
    def getRealUrl(url: str, proxies: Union[dict, None] = None) -> Union[str, None]:
        """
        获取真实URL
        :param url: 链接地址
        :param proxies: 代理
        :return: str
        """
        try:
            response = requests.head(
                url=url, headers=UrlUtils.headers,
                allow_redirects=False, verify=False, proxies=proxies
            )

            if response.status_code == 400:  # Bad Requests
                # TODO 报错处理
                logger.error("HTTP status code 400, it seems that the url is unavailable")
                return

            while response.status_code == 302:  # 当302的时候
                rs = response.headers["location"]  # 获取重定向信息
                logger.info(f'HTTP status code:302, Headers["Location"] is: {rs}')
                # 看它返回的是不是完整的URL
                t = UrlUtils.urlRe.search(rs)
                if t:  # 是的话直接跳转
                    url = rs
                elif not t:  # 不是在前面加上URL
                    url = re.findall(r"((?:https?|ftp)://[\s\S]*?)/", url)
                    url = url[0] + rs

                    logger.info(f"HTTP status code:302, Redirect to {url}")

                response = requests.head(url=url, headers=UrlUtils.headers, allow_redirects=False, verify=False,
                                        proxies=proxies)  # 再访问一次

            return url

        # TODO 报错处理
        except requests.exceptions.ConnectionError as err:
            logger.error(f"Cannot connect to the Internet! Error: {err}")
            return
        except ValueError as err:
            logger.error(f"Cannot connect to the Internet! Error: {err}")
            return
