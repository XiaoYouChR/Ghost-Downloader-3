from pathlib import Path

from app.gui.task_list import TaskItem


def test_speedText_formatsBytesPerSecond():
    item = TaskItem({"taskId": "x", "title": "t", "status": "RUNNING", "speed": 1024})
    assert item.speedText == "1.00 KB/s"


def test_speedText_emptyWhenIdle():
    item = TaskItem({"taskId": "x", "title": "t", "status": "WAITING", "speed": 0})
    assert item.speedText == ""


def test_progressText_showsReceivedOverTotal():
    item = TaskItem({"taskId": "x", "title": "t", "status": "RUNNING", "fileSize": 10485760, "received": 1536})
    assert item.progressText == "1.50 KB / 10.00 MB"


def test_progressText_emptyWhenSizeUnknown():
    item = TaskItem({"taskId": "x", "title": "t", "status": "RUNNING", "fileSize": 0})
    assert item.progressText == ""


def test_completed_reflectsStatus():
    assert TaskItem({"taskId": "x", "title": "t", "status": "COMPLETED"}).completed is True
    assert TaskItem({"taskId": "x", "title": "t", "status": "RUNNING"}).completed is False


def test_output_joinsPathAndTitle():
    item = TaskItem({"taskId": "x", "title": "movie.mp4", "status": "COMPLETED", "path": "/downloads"})
    assert item.output == str(Path("/downloads") / "movie.mp4")


def test_errorText_fromWire():
    assert TaskItem({"taskId": "x", "title": "t", "status": "FAILED", "error": "timeout"}).errorText == "timeout"
    assert TaskItem({"taskId": "x", "title": "t", "status": "RUNNING"}).errorText == ""


def test_chips_fromWire():
    # pack 专属展示由引擎算成 chip 列表过缝；gui 原样转给卡片的 Repeater，核心不认识具体 pack。
    item = TaskItem({"taskId": "x", "title": "t", "status": "RUNNING", "chips": ["Peers 5 / Seeds 2", "↑ 1.00 KB/s"]})
    assert item.chips == ["Peers 5 / Seeds 2", "↑ 1.00 KB/s"]
    assert TaskItem({"taskId": "x", "title": "t", "status": "RUNNING"}).chips == []


def test_typeIcon_picksByExtension():
    def icon(name: str) -> str:
        return TaskItem({"taskId": "x", "title": name, "status": "RUNNING"}).typeIcon

    assert icon("movie.mp4") == "ic_fluent_video_clip_20_filled"
    assert icon("pack.zip") == "ic_fluent_folder_zip_20_filled"
    assert icon("song.flac") == "ic_fluent_music_note_2_20_filled"
    assert icon("setup.exe") == "ic_fluent_window_apps_20_filled"


def test_typeIcon_defaultsToDocument():
    item = TaskItem({"taskId": "x", "title": "README", "status": "RUNNING"})
    assert item.typeIcon == "ic_fluent_document_20_filled"


def test_leftTimeText_estimatesFromSpeed():
    item = TaskItem({"taskId": "x", "title": "t", "status": "RUNNING", "fileSize": 10000, "received": 2000, "speed": 1000})
    assert item.leftTimeText == "8s"  # 剩余 8000 / 1000B每秒 = 8 秒


def test_leftTimeText_dashWhenNotRunningOrStalled():
    paused = TaskItem({"taskId": "x", "title": "t", "status": "PAUSED", "fileSize": 10000, "received": 2000, "speed": 0})
    stalled = TaskItem({"taskId": "x", "title": "t", "status": "RUNNING", "fileSize": 10000, "received": 2000, "speed": 0})
    assert paused.leftTimeText == "--"
    assert stalled.leftTimeText == "--"
