"""parseError / parseDiagnostic 的错误解析测试。

Seam: parseError — 输入 N_m3u8DL-RE 完整 stdout 和 exit code，
输出 TaskError（分类消息 + detail）。
"""
from features.m3u8_pack.task import parseDiagnostic, parseError


# -- parseDiagnostic ----------------------------------------------------------

class TestParseDiagnostic:

    def test_extracts_last_warn_line(self):
        output = (
            "22:17:47.595 INFO : N_m3u8DL-RE (Beta version) 20260628\n"
            "22:17:48.730 WARN : Response status code does not indicate success: 403 (Forbidden). (1/10)\n"
            "22:17:50.235 INFO : Loading URL: http://example.com\n"
            "22:17:51.306 WARN : Response status code does not indicate success: 403 (Forbidden). (2/10)\n"
        )
        assert parseDiagnostic(output) == (
            "Response status code does not indicate success: 403 (Forbidden). (2/10)"
        )

    def test_prefers_error_over_warn(self):
        output = (
            "22:17:48.730 WARN : some warning\n"
            "22:18:00.000 ERROR: ffmpeg not found\n"
        )
        assert parseDiagnostic(output) == "ffmpeg not found"

    def test_ignores_info_lines(self):
        output = "22:17:47.595 INFO : N_m3u8DL-RE started\n"
        assert parseDiagnostic(output) == ""

    def test_ignores_stack_trace_lines(self):
        output = (
            "22:18:14.893 WARN : 403 (Forbidden). (10/10)\n"
            "Unhandled exception: System.Exception: Failed\n"
            " ---> System.Net.Http.HttpRequestException: 403\n"
            "   at System.Net.Http.EnsureSuccessStatusCode()\n"
        )
        assert parseDiagnostic(output) == "403 (Forbidden). (10/10)"

    def test_concatenated_warn_and_unhandled_exception(self):
        output = (
            "22:18:14.893 WARN : 403 (Forbidden). (10/10)"
            "Unhandled exception: System.Exception: Failed\n"
            " ---> System.Net.Http.HttpRequestException: 403\n"
        )
        result = parseDiagnostic(output)
        assert "403 (Forbidden). (10/10)" in result

    def test_empty_output(self):
        assert parseDiagnostic("") == ""

    def test_error_colon_no_space(self):
        output = "22:18:00.000 ERROR: Failed\n"
        assert parseDiagnostic(output) == "Failed"


# -- parseError ---------------------------------------------------------------

class TestParseError:

    def test_matches_403(self):
        output = (
            "22:18:14.893 WARN : Response status code does not indicate success: "
            "403 (Forbidden). (10/10)\n"
        )
        error = parseError(output, 1)
        assert "403" in str(error)
        assert "服务器拒绝了请求" in error.message

    def test_matches_404(self):
        output = (
            "22:18:14.893 WARN : Response status code does not indicate success: "
            "404 (Not Found). (3/10)\n"
        )
        error = parseError(output, 1)
        assert "资源不存在" in error.message

    def test_matches_generic_http_error(self):
        output = (
            "22:18:14.893 WARN : Response status code does not indicate success: "
            "500 (Internal Server Error). (1/10)\n"
        )
        error = parseError(output, 1)
        assert "服务器返回了错误" in error.message

    def test_matches_dns_failure(self):
        output = "22:18:00.000 WARN : No such host is known. (1/10)\n"
        error = parseError(output, 1)
        assert "无法解析域名" in error.message

    def test_matches_connection_refused(self):
        output = "22:18:00.000 WARN : Connection refused (1/10)\n"
        error = parseError(output, 1)
        assert "连接被拒绝" in error.message

    def test_matches_timeout(self):
        output = (
            "22:18:00.000 WARN : The request was canceled due to the configured "
            "HttpClient.Timeout (1/10)\n"
        )
        error = parseError(output, 1)
        assert "连接超时" in error.message

    def test_matches_ssl_error(self):
        output = (
            "22:18:00.000 WARN : The SSL connection could not be established (1/10)\n"
        )
        error = parseError(output, 1)
        assert "SSL 连接失败" in error.message

    def test_fallback_with_diagnostic(self):
        output = "22:18:00.000 ERROR: some unknown error\n"
        error = parseError(output, 1)
        assert "进程异常退出" in error.message
        assert error.params["detail"] == "some unknown error"
        assert error.params["code"] == 1

    def test_fallback_empty_output(self):
        error = parseError("", 1)
        assert "进程异常退出" in error.message
        assert error.params["detail"] == "N_m3u8DL-RE"

    def test_403_specific_beats_generic_http(self):
        output = (
            "22:18:14.893 WARN : Response status code does not indicate success: "
            "403 (Forbidden). (10/10)\n"
        )
        error = parseError(output, 1)
        assert "服务器拒绝了请求" in error.message
        assert "服务器返回了错误" not in error.message

    def test_detail_contains_diagnostic(self):
        output = (
            "22:18:14.893 WARN : Response status code does not indicate success: "
            "403 (Forbidden). (10/10)\n"
            "Unhandled exception: System.Exception: Failed\n"
            " ---> System.Net.Http.HttpRequestException: 403\n"
            "   at System.Net.Http.EnsureSuccessStatusCode()\n"
        )
        error = parseError(output, 1)
        assert "403 (Forbidden). (10/10)" in error.params["detail"]

    def test_not_supported_exception(self):
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

    def test_file_not_found_exception(self):
        output = (
            "17:07:01.414 INFO : N_m3u8DL-RE (Beta version) 20260628\n"
            "Unhandled exception: System.IO.FileNotFoundException: "
            "ffmpeg not found, please download at: https://ffmpeg.org\n"
            "   at N_m3u8DL_RE.Program.<DoWorkAsync>d__3.MoveNext()\n"
        )
        error = parseError(output, 1)
        assert "缺少依赖程序" in error.message

    def test_unhandled_exception_fallback_diagnostic(self):
        """无 WARN/ERROR 行时从 Unhandled exception 提取 detail。"""
        output = (
            "17:07:01.414 INFO : N_m3u8DL-RE started\n"
            "Unhandled exception: System.Exception: something went wrong\n"
            "   at SomeNamespace.SomeMethod()\n"
        )
        error = parseError(output, 1)
        assert error.params["detail"] == "something went wrong"
