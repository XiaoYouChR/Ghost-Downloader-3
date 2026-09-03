from app.site_rules import defaultSiteRules, matchingSiteRule, publicSiteRules, validateSiteRule


def test_default_rules_cover_known_sites():
    rules = defaultSiteRules()
    assert matchingSiteRule("https://pixeldrain.com/u/example", rules)["action"] == "pixeldrain_api"
    assert matchingSiteRule("https://www.uupdump.net/download.php?id=x", rules)["action"] == "uupdump_post"
    assert matchingSiteRule("https://hdsex.org/shemale/video/776062386?x=1", rules)["action"] == "prefer_latest_hls"


def test_disabled_rule_does_not_match():
    rules = defaultSiteRules()
    rules[0]["enabled"] = False
    assert matchingSiteRule("https://pixeldrain.com/u/example", rules) is None


def test_public_rules_strip_desktop_only_fields():
    rules = publicSiteRules(defaultSiteRules())
    assert all(set(rule) == {"id", "name", "hosts", "action", "enabled"} for rule in rules)
    assert all("description" not in rule and "connections" not in rule for rule in rules)


def test_full_default_rules_are_valid():
    assert all(validateSiteRule(rule) for rule in defaultSiteRules())
