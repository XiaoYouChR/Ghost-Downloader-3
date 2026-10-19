from features.m3u8_pack.task import parseDiagnostic, parseError


# -- parseDiagnostic ----------------------------------------------------------


def test_parse_detail_from_last_warning():
    output = (
        "22:17:47.595 INFO : N_m3u8DL-RE (Beta version) 20260628\n"
        "22:17:48.730 WARN : Response status code does not indicate success: 403 (Forbidden). (1/10)\n"
        "22:17:50.235 INFO : Loading URL: http://example.com\n"
        "22:17:51.306 WARN : Response status code does not indicate success: 403 (Forbidden). (2/10)\n"
    )
    assert parseDiagnostic(output) == (
        "Response status code does not indicate success: 403 (Forbidden). (2/10)"
    )


def test_parse_prefers_error_over_warning():
    output = (
        "22:17:48.730 WARN : some warning\n"
        "22:18:00.000 ERROR: ffmpeg not found\n"
    )
    assert parseDiagnostic(output) == "ffmpeg not found"


def test_parse_skips_stack_trace():
    output = (
        "22:18:14.893 WARN : 403 (Forbidden). (10/10)\n"
        "Unhandled exception: System.Exception: Failed\n"
        " ---> System.Net.Http.HttpRequestException: 403\n"
        "   at System.Net.Http.EnsureSuccessStatusCode()\n"
    )
    assert parseDiagnostic(output) == "403 (Forbidden). (10/10)"


def test_parse_warning_glued_to_exception():
    output = (
        "22:18:14.893 WARN : 403 (Forbidden). (10/10)"
        "Unhandled exception: System.Exception: Failed\n"
        " ---> System.Net.Http.HttpRequestException: 403\n"
    )
    result = parseDiagnostic(output)
    assert "403 (Forbidden). (10/10)" in result

# -- parseError ---------------------------------------------------------------


def test_parse_403():
    output = (
        "22:18:14.893 WARN : Response status code does not indicate success: "
        "403 (Forbidden). (10/10)\n"
    )
    error = parseError(output, 1)
    assert "403" in str(error)
    assert "服务器拒绝了请求" in error.message


def test_parse_404():
    output = (
        "22:18:14.893 WARN : Response status code does not indicate success: "
        "404 (Not Found). (3/10)\n"
    )
    error = parseError(output, 1)
    assert "资源不存在" in error.message


def test_parse_other_http_error():
    output = (
        "22:18:14.893 WARN : Response status code does not indicate success: "
        "500 (Internal Server Error). (1/10)\n"
    )
    error = parseError(output, 1)
    assert "服务器返回了错误" in error.message


def test_parse_dns_failure():
    output = "22:18:00.000 WARN : No such host is known. (1/10)\n"
    error = parseError(output, 1)
    assert "无法解析域名" in error.message


def test_parse_connection_refused():
    output = "22:18:00.000 WARN : Connection refused (1/10)\n"
    error = parseError(output, 1)
    assert "连接被拒绝" in error.message


def test_parse_timeout():
    output = (
        "22:18:00.000 WARN : The request was canceled due to the configured "
        "HttpClient.Timeout (1/10)\n"
    )
    error = parseError(output, 1)
    assert "连接超时" in error.message


def test_parse_ssl_failure():
    output = (
        "22:18:00.000 WARN : The SSL connection could not be established (1/10)\n"
    )
    error = parseError(output, 1)
    assert "SSL 连接失败" in error.message


def test_parse_unknown_error_keeps_detail():
    output = "22:18:00.000 ERROR: some unknown error\n"
    error = parseError(output, 1)
    assert "进程异常退出" in error.message
    assert error.params["detail"] == "some unknown error"
    assert error.params["code"] == 1


def test_parse_prefers_403():
    output = (
        "22:18:14.893 WARN : Response status code does not indicate success: "
        "403 (Forbidden). (10/10)\n"
    )
    error = parseError(output, 1)
    assert "服务器拒绝了请求" in error.message
    assert "服务器返回了错误" not in error.message


def test_parse_keeps_detail():
    output = (
        "22:18:14.893 WARN : Response status code does not indicate success: "
        "403 (Forbidden). (10/10)\n"
        "Unhandled exception: System.Exception: Failed\n"
        " ---> System.Net.Http.HttpRequestException: 403\n"
        "   at System.Net.Http.EnsureSuccessStatusCode()\n"
    )
    error = parseError(output, 1)
    assert "403 (Forbidden). (10/10)" in error.params["detail"]


def test_parse_unsupported_stream():
    """Windows 日志回归：NotSupportedException 无 WARN/ERROR 行。"""
    output = (
        "17:07:01.414 INFO : \xd8\xb6, ANSI\xc9\xab\n"
        "17:07:01.419 INFO : N_m3u8DL-RE (Beta version) 20260628\n"
        "17:07:01.419 INFO : URL: https://example.com/index.m3u8\n"
        "Unhandled exception: System.NotSupportedException: garbled text\n"
        "   at N_m3u8DL_RE.Parser.StreamExtractor.LoadSourceFromText(String) + 0x282\n"
        "   at System.CommandLine.Invocation.InvocationPipeline.<InvokeAsync>d__0.MoveNext()\n"
    )
    error = parseError(output, 1)
    assert "不是有效的播放列表" in error.message
    assert error.params["detail"] == "garbled text"


def test_parse_file_not_found():
    output = (
        "17:07:01.414 INFO : N_m3u8DL-RE (Beta version) 20260628\n"
        "Unhandled exception: System.IO.FileNotFoundException: "
        "ffmpeg not found, please download at: https://ffmpeg.org\n"
        "   at N_m3u8DL_RE.Program.<DoWorkAsync>d__3.MoveNext()\n"
    )
    error = parseError(output, 1)
    assert "缺少依赖程序" in error.message


def test_parse_unhandled_exception():
    """无 WARN/ERROR 行时从 Unhandled exception 提取 detail。"""
    output = (
        "17:07:01.414 INFO : N_m3u8DL-RE started\n"
        "Unhandled exception: System.Exception: something went wrong\n"
        "   at SomeNamespace.SomeMethod()\n"
    )
    error = parseError(output, 1)
    assert error.params["detail"] == "something went wrong"
