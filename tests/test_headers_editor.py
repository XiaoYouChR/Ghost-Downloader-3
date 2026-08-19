from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog, QWidget
from qfluentwidgets import TeachingTip

from app.view.components.headers_editor import HEADER_ROW_HEIGHT, HeadersEditor
from app.view.dialogs.headers_preset_edit import HeadersPresetEditDialog


def test_header_rows_stay_compact(qapp, qtbot):
    editor = HeadersEditor(defaults={})
    qtbot.addWidget(editor)
    editor.resize(500, 400)
    editor.setHeaders({"accept": "*/*", "cookie": "session=1"})
    editor.show()
    qapp.processEvents()

    rows = editor._rows()

    assert len(rows) == 3
    assert all(row.height() == HEADER_ROW_HEIGHT for row in rows)
    assert rows[1].y() - rows[0].y() == HEADER_ROW_HEIGHT + editor.tableLayout.spacing()


@pytest.mark.parametrize("result", [QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected])
def test_header_help_closes_with_dialog(result, qapp, qtbot):
    parent = QWidget()
    parent.resize(900, 700)
    qtbot.addWidget(parent)
    dialog = HeadersPresetEditDialog(
        parent,
        preset={"name": "Default", "headers": {"accept": "*/*"}},
    )
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.editor._onHelpClicked()
    qapp.processEvents()

    tips = dialog.editor.findChildren(TeachingTip)
    assert len(tips) == 1
    assert tips[0].isVisible()

    dialog.done(result)
    qapp.processEvents()

    assert dialog.editor.findChildren(TeachingTip) == []
