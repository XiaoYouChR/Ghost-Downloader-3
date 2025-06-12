
async def getLinkInfo(url: str, headers: dict, fileName: str = "", verify: bool = cfg.SSLVerify.value, proxy: str = "", followRedirects: bool = True) -> tuple:
    if not proxy:
        proxy = getProxy()
    headers = headers.copy()
    headers["Range"] = "bytes=0-"#尝试发送范围请求
    # 使用 stream 请求获取响应, 反爬
    with httpx.stream("GET", url, headers=headers, verify=verify, proxy=proxy, follow_redirects=followRedirects, trust_env=False) as response:
        response.raise_for_status()  # 如果状态码不是 2xx，抛出异常

        head = response.headers

        url = str(response.url)

        # 获取文件大小, 判断是否可以分块下载
        # 状态码为206才是范围请求，200表示服务器拒绝了范围请求同时将发送整个文件
        if response.status_code == 206 and "content-range" in head:
            #https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Reference/Headers/Content-Range
            _left, _char, right = head["content-range"].rpartition("/")

            if right != "*":
                fileSize = int(right)
                logger.info(f"content-range: {head['content-range']}, fileSize: {fileSize}, content-length: {head['content-length']}")

            elif "content-length" in head:
                fileSize = int(head["content-length"])

            else:
                fileSize = 0
                logger.info("文件似乎支持续传，但无法获取文件大小")
        else:
            fileSize = 0
            logger.info("文件不支持续传")

        # 获取文件名
        if not fileName:
            try:
                # 尝试处理 Content-Disposition 中的 fileName* (RFC 5987 格式)
                headerValue = head["content-disposition"]
                if 'fileName*' in headerValue:
                    match = re.search(r'filename\*\s*=\s*([^;]+)', headerValue, re.IGNORECASE)
                    if match:
                        fileName = match.group(1)
                        fileName = decode_rfc2231(fileName)[2]  # fileName* 后的部分是编码信息

                # 如果 fileName* 没有成功获取，尝试处理普通的 fileName
                if not fileName and 'filename' in headerValue:
                    match = re.search(r'filename\s*=\s*["\']?([^"\';]+)["\']?', headerValue, re.IGNORECASE)
                    if match:
                        fileName = match.group(1)

                # 移除文件名头尾可能存在的引号并解码
                if fileName:
                    fileName = unquote(fileName)
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
                    fileName = \
                        unquote(parse_qs(urlparse(url).query).get('response-content-disposition', [''])[0]).split(
                            "filename=")[-1]

                    # 移除文件名头尾可能存在的引号并解码
                    if fileName:
                        fileName = unquote(fileName)
                        fileName = fileName.strip('"\'')
                    else:
                        raise KeyError

                    logger.debug(f"方法2获取文件名成功, 文件名:{fileName}")

                except (KeyError, IndexError) as e:

                    logger.info(f"方法2获取文件名失败, KeyError or IndexError:{e}")
                    fileName = unquote(urlparse(url).path.split('/')[-1])

                    if fileName:  # 如果没有后缀名，则使用 content-type 作为后缀名
                        _ = fileName.split('.')
                        if len(_) == 1:
                            fileName += '.' + head["content-type"].split('/')[-1].split(';')[0]

                        logger.debug(f"方法3获取文件名成功, 文件名:{fileName}")
                    else:
                        logger.debug("方法3获取文件名失败, 文件名为空")
                        # 什么都 Get 不到的情况
                        logger.info(f"获取文件名失败, 错误:{e}")
                        content_type = head["content-type"].split('/')[-1].split(';')[0]
                        fileName = f"downloaded_file{int(time_ns())}.{content_type}"
                        logger.debug(f"方法4获取文件名成功, 文件名:{fileName}")

    return url, fileName, fileSize
