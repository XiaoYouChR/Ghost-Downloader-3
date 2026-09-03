from features.http_pack.pack import parsePixelDrainUrl, parseUupDumpUrl


def test_pixeldrain_viewer_url_becomes_api_download():
    assert parsePixelDrainUrl("https://pixeldrain.com/u/abc123") == (
        "https://pixeldrain.com/api/file/abc123?download",
        "https://pixeldrain.com/u/abc123",
    )


def test_uupdump_download_url_becomes_post_endpoint():
    url = (
        "https://uupdump.net/download.php?"
        "id=c1c737c2-f2d9-4824-bb5b-1af515179099&"
        "pack=pt-br&edition=professional"
    )

    assert parseUupDumpUrl(url) == (
        "https://uupdump.net/get.php?"
        "id=c1c737c2-f2d9-4824-bb5b-1af515179099&"
        "pack=pt-br&edition=professional",
        url,
    )
