from features.http_pack.site_rules import (
    UUPDUMP_BODY,
    UUPDUMP_CONTENT_TYPE,
    _filename_from_content_disposition,
    _uupdump_urls,
    apply_http_site_rule,
)


def test_uupdump_download_url_becomes_get_post_endpoint():
    url = "https://uupdump.net/download.php?id=abc&pack=pt-br&edition=professional"
    download, referer = _uupdump_urls(url)
    assert download == "https://uupdump.net/get.php?id=abc&pack=pt-br&edition=professional"
    assert referer == url


def test_uupdump_rule_preserves_query_and_sets_post_identity():
    url = "https://www.uupdump.net/download.php?id=abc&pack=pt-br"
    rule = apply_http_site_rule(url, {"Cookie": "session=123"}, 8)
    assert rule.action == "uupdump_post"
    assert rule.url == "https://uupdump.net/get.php?id=abc&pack=pt-br"
    assert rule.subworkerCount == 1
    assert rule.requestBody == UUPDUMP_BODY
    assert rule.requestContentType == UUPDUMP_CONTENT_TYPE
    assert rule.headers["Referer"] == "https://uupdump.net/download.php?id=abc&pack=pt-br"
    assert rule.headers["Origin"] == "https://uupdump.net"
    assert rule.headers["Cookie"] == "session=123"


def test_uupdump_content_disposition_filename():
    assert _filename_from_content_disposition('attachment; filename="26100.1_amd64_pt-br_multi.iso"') == "26100.1_amd64_pt-br_multi.iso"


def test_uupdump_content_disposition_rfc2231_filename():
    assert _filename_from_content_disposition("attachment; filename*=UTF-8''Windows%2011%20pt-BR.iso") == "Windows 11 pt-BR.iso"


def test_similar_uupdump_hostname_does_not_match():
    rule = apply_http_site_rule("https://uupdump.net.example.com/download.php?id=abc", {}, 8)
    assert rule.action == "standard"


def test_pixeldrain_forces_one_connection():
    rule = apply_http_site_rule("https://pixeldrain.com/api/file/FhcC8Fyd?download", {}, 8)
    assert rule.action == "single_connection"
    assert rule.subworkerCount == 1


def test_pixeldrain_subdomain_also_matches():
    rule = apply_http_site_rule("https://cdn.pixeldrain.com/api/file/example", {}, 16)
    assert rule.action == "single_connection"
    assert rule.subworkerCount == 1
