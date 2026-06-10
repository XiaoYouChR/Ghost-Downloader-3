from app.protocol.message import Command, Event


def test_command_bytesRoundTrip():
    command = Command("addTask", {"url": "https://example.com/a.mp4"})
    assert Command.fromBytes(command.toBytes()) == command


def test_event_bytesRoundTrip():
    event = Event("taskAdded", {"task": {"taskId": "t1", "title": "a.mp4"}})
    assert Event.fromBytes(event.toBytes()) == event


def test_command_emptyData():
    command = Command("attach")
    assert Command.fromBytes(command.toBytes()) == Command("attach", {})
