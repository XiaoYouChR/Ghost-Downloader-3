from orjson import loads

from app.gui.browser_service import BrowserService, _Session


class _FakeSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def sendTextMessage(self, message: str) -> None:
        self.sent.append(loads(message))


def _service(spine):
    return BrowserService(spine.backend, token="secret"), _Session(_FakeSocket())


def test_helloWithValidTokenAuthenticates(spine):
    service, session = _service(spine)
    service.dispatch(session, {"type": "hello", "protocolVersion": 1, "token": "secret"})

    assert session.authenticated is True
    assert session.socket.sent[-1]["type"] == "hello_ack"


def test_helloWithBadTokenRejected(spine):
    service, session = _service(spine)
    service.dispatch(session, {"type": "hello", "token": "wrong"})

    assert session.authenticated is False
    assert session.socket.sent[-1]["code"] == "unauthorized"


def test_createTaskBeforeAuthIsRejected(spine):
    service, session = _service(spine)
    service.dispatch(session, {"type": "create_task", "requestId": "r1",
                               "payload": {"url": "https://example.com/a.zip"}})

    assert spine.taskList.rowCount() == 0  # 没认证不收
    assert session.socket.sent[-1]["code"] == "unauthorized"


def test_createTaskAddsThroughBackend(spine):
    service, session = _service(spine)
    service.dispatch(session, {"type": "hello", "token": "secret"})
    service.dispatch(session, {"type": "create_task", "requestId": "r1",
                               "payload": {"url": "https://example.com/a.zip"}})

    assert spine.taskList.rowCount() == 1  # 扩展发来的链接落成任务
    assert session.socket.sent[-1] == {"type": "create_task_result", "requestId": "r1", "ok": True}


def test_pairApproveSendsToken(spine):
    service, session = _service(spine)
    captured = []
    service.pairRequested.connect(lambda info: captured.append(info))

    service.dispatch(session, {"type": "pair_request", "requestId": "p1", "extensionVersion": "1.2"})
    assert captured and captured[-1]["extensionVersion"] == "1.2"  # 弹框信息给了 QML

    service.approvePair()
    result = session.socket.sent[-1]
    assert result["ok"] is True and result["token"] == "secret"
