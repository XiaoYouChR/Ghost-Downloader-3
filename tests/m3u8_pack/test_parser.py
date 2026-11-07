import asyncio

import pytest

from app.models.task import TaskError, TaskOptions
from features.m3u8_pack.pack import M3U8Parser


def test_parse_malformed_key_raises_readable_error(tmp_path):
    # 真实样本：服务器把 METHOD 拼成了 MEATHOD (#976)
    manifest = tmp_path / "index.m3u8"
    manifest.write_text(
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-TARGETDURATION:17\n"
        '#EXT-X-KEY:MEATHOD=AES-128,URI="https://example.com/key"\n'
        "#EXTINF:10.0,\n"
        "https://example.com/0.ts\n"
        "#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )

    with pytest.raises(TaskError) as info:
        asyncio.run(M3U8Parser().parse(TaskOptions(url=manifest.as_uri(), outputFolder=tmp_path, headers={})))

    assert "加密" in info.value.message
