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
