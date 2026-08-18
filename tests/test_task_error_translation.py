from PySide6.QtCore import QTranslator

from app.view.error_catalog import translateTaskError


class TaskErrorTranslator(QTranslator):
    translations = {
        "该种子已在下载中": "This torrent is already being downloaded",
        "该 eD2k 链接已在下载中": "This eD2k link is already being downloaded",
    }

    def translate(self, context, sourceText, disambiguation=None, n=-1):
        if context == "TaskErrors":
            return self.translations.get(sourceText, "")
        return ""


def test_task_error_translation_uses_shared_catalog(qapp):
    translator = TaskErrorTranslator()
    qapp.installTranslator(translator)
    try:
        assert translateTaskError("该种子已在下载中") == (
            "This torrent is already being downloaded"
        )
        assert translateTaskError("该 eD2k 链接已在下载中") == (
            "This eD2k link is already being downloaded"
        )
        assert translateTaskError("uncatalogued external error") == (
            "uncatalogued external error"
        )
    finally:
        qapp.removeTranslator(translator)


def test_add_task_popup_translates_parse_error(monkeypatch):
    from app.view.dialogs import task_draft as draft_module

    captured = {}

    class Dialog:
        def _refreshStats(self):
            pass

        def tr(self, text):
            return text

    def capture(*args, **kwargs):
        captured["content"] = args[1]

    monkeypatch.setattr(draft_module, "translateTaskError", lambda _: "translated error")
    monkeypatch.setattr(draft_module.InfoBar, "error", capture)

    draft_module.TaskDraftDialog._onParseFailed(Dialog(), "ed2k://example", "source error")

    assert captured["content"] == "ed2k://example\ntranslated error"


def test_edit_task_popup_translates_parse_error(monkeypatch):
    from app.view.dialogs import edit_task as edit_module

    captured = {}

    class Dialog:
        _pendingParseId = "pending"

        def _setInteractive(self, enabled):
            self.enabled = enabled

        def tr(self, text):
            return text

    def capture(*args, **kwargs):
        captured["content"] = kwargs["content"]

    dialog = Dialog()
    monkeypatch.setattr(edit_module, "translateTaskError", lambda _: "translated error")
    monkeypatch.setattr(edit_module.InfoBar, "error", capture)

    edit_module.LiveEditDialog._onReparseFailed(dialog, "source error")

    assert captured["content"] == "translated error"
    assert dialog._pendingParseId == ""
    assert dialog.enabled is True
