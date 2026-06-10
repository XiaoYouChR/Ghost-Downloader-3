from app.gui.clipboard import parseDownloadableUrls


def test_picksHttpUrl():
    assert parseDownloadableUrls("https://example.com/file.zip") == ["https://example.com/file.zip"]


def test_picksMagnet():
    link = "magnet:?xt=urn:btih:777695049623a1cd052bd6b175b40e6540ce74ca"
    assert parseDownloadableUrls(link) == [link]


def test_picksFtp():
    assert parseDownloadableUrls("ftp://host:21/path") == ["ftp://host:21/path"]


def test_skipsPlainText():
    assert parseDownloadableUrls("随便复制的一段话，不是链接") == []


def test_skipsNonDownloadableScheme():
    # file:// / mailto: 不是可下载链接
    assert parseDownloadableUrls("file:///c:/x.txt\nmailto:a@b.com") == []


def test_trimsWhitespace():
    assert parseDownloadableUrls("  https://a.com/x  ") == ["https://a.com/x"]


def test_collectsMultipleLinesSkippingNoise():
    text = "https://a.com/1.zip\n这行是说明\nmagnet:?xt=urn:btih:abc\n\nhttps://b.com/2.bin"
    assert parseDownloadableUrls(text) == [
        "https://a.com/1.zip",
        "magnet:?xt=urn:btih:abc",
        "https://b.com/2.bin",
    ]


def test_rejectsMalformedHttp():
    # 没有主机名的 http 不算
    assert parseDownloadableUrls("http://") == []
