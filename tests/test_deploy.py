from __future__ import annotations

from pathlib import Path

import pytest

from scripts.deploy import buildArgs, findQfwModules


EXPORTS = {
    "qfluentwidgets": {
        "PushButton": "qfluentwidgets.components.widgets.button",
        "load": "qfluentwidgets.common.runtime",
    },
    "qfluentwidgets.common": {
        "qrouter": "qfluentwidgets.common.router",
    },
}


def test_resolve_package_exports(tmp_path: Path):
    source = tmp_path / "sample.py"
    source.write_text(
        "from qfluentwidgets import PushButton, load\n"
        "from qfluentwidgets.common import qrouter\n"
        "from qfluentwidgets.common.style_sheet import updateStyleSheet\n",
        encoding="utf-8",
    )

    assert findQfwModules([source], EXPORTS) == {
        "qfluentwidgets.components.widgets.button",
        "qfluentwidgets.common.runtime",
        "qfluentwidgets.common.router",
        "qfluentwidgets.common.style_sheet",
    }


def test_ignore_type_checking_imports(tmp_path: Path):
    source = tmp_path / "typed.py"
    source.write_text(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from qfluentwidgets import PushButton\n",
        encoding="utf-8",
    )

    assert findQfwModules([source], EXPORTS) == set()


def test_reject_bare_import(tmp_path: Path):
    source = tmp_path / "bare.py"
    source.write_text("import qfluentwidgets\n", encoding="utf-8")

    with pytest.raises(ValueError, match="from qfluentwidgets import"):
        findQfwModules([source], EXPORTS)


def test_reject_wildcard_import(tmp_path: Path):
    source = tmp_path / "star.py"
    source.write_text("from qfluentwidgets import *\n", encoding="utf-8")

    with pytest.raises(ValueError, match="wildcard"):
        findQfwModules([source], EXPORTS)


def test_reject_unknown_symbol(tmp_path: Path):
    source = tmp_path / "unknown.py"
    source.write_text("from qfluentwidgets import DoesNotExist\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown qfluentwidgets symbol"):
        findQfwModules([source], EXPORTS)


def test_build_args_shakes_qfw():
    args = buildArgs()

    assert "--include-package=qfluentwidgets" not in args
    assert "--include-module=qfluentwidgets.common.runtime" in args
    assert "--include-module=qfluentwidgets.window.splash_screen" in args
    assert "--include-module=qfluentwidgets.window.fluent_window" in args
    assert "--include-module=qfluentwidgets.multimedia.media_player" not in args
    assert "--include-module=qfluentwidgets.components.widgets.tab_view" not in args
    assert "--report=dist/compilation-report.xml" in args
