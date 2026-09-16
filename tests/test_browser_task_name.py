"""toTaskName 的命名合并测试。

Seam: toTaskName — 输入浏览器扩展给的 title 和解析器定好的任务名，
输出最终任务名。
"""
from app.services.browser_service import toTaskName


class TestToTaskName:

    def test_replaces_manifest_suffix_with_container_suffix(self):
        assert toTaskName("My Show.m3u8", "index.mp4") == "My Show.mp4"

    def test_replaces_manifest_suffix_for_dash(self):
        assert toTaskName("My Show.mpd", "manifest.mp4") == "My Show.mp4"

    def test_replaces_manifest_suffix_ignoring_case(self):
        assert toTaskName("My Show.M3U8", "index.mp4") == "My Show.mp4"

    def test_uses_configured_container_suffix(self):
        assert toTaskName("My Show.m3u8", "index.mkv") == "My Show.mkv"

    def test_uses_live_container_suffix(self):
        assert toTaskName("My Show.m3u8", "index.ts") == "My Show.ts"

    def test_keeps_title_already_carrying_the_container_suffix(self):
        assert toTaskName("My Show.mp4", "index.mp4") == "My Show.mp4"

    def test_keeps_manifest_title_when_the_manifest_is_the_download(self):
        assert toTaskName("playlist.m3u8", "playlist.m3u8") == "playlist.m3u8"

    def test_keeps_a_suffix_that_is_not_a_manifest(self):
        assert toTaskName("S01E01.1080p", "video.mp4") == "S01E01.1080p.mp4"

    def test_keeps_title_when_the_parsed_name_has_no_suffix(self):
        assert toTaskName("My Show.m3u8", "index") == "My Show.m3u8"

    def test_appends_container_suffix_to_a_plain_title(self):
        assert toTaskName("My Show", "index.mp4") == "My Show.mp4"
