"""QFluentWidgets 字符串按基类 context 回退 — #362。"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="ru_RU">
<context>
    <name>MessageBoxBase</name>
    <message>
        <source>OK</source>
        <translation>ОК</translation>
    </message>
</context>
<context>
    <name>EditTaskDialog</name>
    <message>
        <source>OK</source>
        <translation>ОК子类</translation>
    </message>
</context>
</TS>
"""


def findLrelease() -> str | None:
    path = shutil.which("pyside6-lrelease")
    if path:
        return path
    candidate = Path(sys.executable).with_name("pyside6-lrelease")
    return str(candidate) if candidate.exists() else None


@pytest.fixture
def translator(qapp, tmp_path):
    from app.translator import FallbackTranslator

    lrelease = findLrelease()
    if lrelease is None:
        pytest.skip("pyside6-lrelease not available")

    ts = tmp_path / "test.ts"
    qm = tmp_path / "test.qm"
    ts.write_text(TS, encoding="utf-8")
    subprocess.run([lrelease, str(ts), "-qm", str(qm)], check=True, capture_output=True)

    translator = FallbackTranslator()
    assert translator.load(str(qm))
    return translator


class TestFallbackTranslator:

    def test_own_context_wins(self, translator):
        assert translator.translate("EditTaskDialog", "OK") == "ОК子类"

    def test_falls_back_to_declaring_context(self, translator):
        assert translator.translate("PlanTaskDialog", "OK") == "ОК"

    def test_unknown_source_is_empty(self, translator):
        assert translator.translate("PlanTaskDialog", "Nope") == ""

    def test_installed_translator_serves_qt(self, qapp, translator):
        from PySide6.QtCore import QCoreApplication

        qapp.installTranslator(translator)
        try:
            assert QCoreApplication.translate("PlanTaskDialog", "OK") == "ОК"
        finally:
            qapp.removeTranslator(translator)
