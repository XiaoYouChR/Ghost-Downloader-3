from __future__ import annotations


def test_match_skips_broken_link(engine, httpPack):
    assert not engine.featureService.match("http://[abc")
