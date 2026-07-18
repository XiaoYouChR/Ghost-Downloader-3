import pytest
from PySide6.QtCore import QLocale

from app.config.cfg import Language
from app.view.mobile.language_dialog import preferredLanguage


@pytest.mark.parametrize(
    ("locale_name", "expected"),
    [
        ("en_US", Language.ENGLISH_UNITED_STATES),
        ("en_GB", Language.ENGLISH_UNITED_STATES),
        ("zh_CN", Language.CHINESE_SIMPLIFIED),
        ("zh_TW", Language.CHINESE_TRADITIONAL),
        ("zh_HK", Language.CANTONESE),
        ("ja_JP", Language.JAPANESE),
        ("ru_RU", Language.RUSSIAN),
        ("pt_PT", Language.PORTUGUESE_BRAZIL),
        ("fr_FR", Language.ENGLISH_UNITED_STATES),
    ],
)
def test_preferred_android_language(locale_name, expected):
    assert preferredLanguage(QLocale(locale_name)) == expected
