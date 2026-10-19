import pytest
from ed2k_pack.lists import parseNodeList, parseServerList


def toU32(value: int) -> bytes:
    return value.to_bytes(4, "little")


def toU16(value: int) -> bytes:
    return value.to_bytes(2, "little")


def buildContact(nodeId: int, size: int) -> bytes:
    return nodeId.to_bytes(16, "little") + bytes(size - 16)


@pytest.mark.parametrize("data, count", [
    (toU32(2) + buildContact(1, 25) + buildContact(2, 25), 2),
    (toU32(0) + toU32(2) + toU32(3) + b"".join(buildContact(i, 34) for i in range(3)), 3),
    (toU32(0) + toU32(3) + toU32(1) + toU32(4) + b"".join(buildContact(i, 25) for i in range(4)), 4),
    (toU32(0) + toU32(3) + toU32(0) + toU32(2) + b"".join(buildContact(i, 34) for i in range(2)), 2),
])
def test_parse_every_nodes_dat_version(data, count):
    assert len(set(parseNodeList(data))) == count


@pytest.mark.parametrize("data", [b"", toU32(5) + bytes(25), toU32(0) + toU32(2) + toU32(0), toU32(0) + toU32(2) + toU32(1) + bytes(25)])
def test_parse_rejects_broken_nodes_dat(data):
    with pytest.raises(ValueError):
        parseNodeList(data)


def buildServer(ip: bytes, port: int) -> bytes:
    tags = [
        b"\x02" + toU16(1) + b"\x01" + toU16(4) + b"name",
        b"\x83\x0c" + toU32(50),
        b"\x03" + toU16(5) + b"users" + toU32(1000),
        b"\x89\x0e\x01",
        b"\x94\x0b" + b"desc",
        b"\x87\x99" + toU32(2) + b"..",
    ]
    return ip + toU16(port) + toU32(len(tags)) + b"".join(tags)


def test_parse_every_server_in_server_met():
    servers = [buildServer(b"\x01\x02\x03\x04", 4661), buildServer(b"\x05\x06\x07\x08", 4242)]
    data = b"\x0e" + toU32(2) + b"".join(servers)

    assert parseServerList(data) == [b"\x01\x02\x03\x04" + toU16(4661), b"\x05\x06\x07\x08" + toU16(4242)]


@pytest.mark.parametrize("data", [
    b"<html>",
    b"\xe0" + toU32(0),
    b"\xe0" + toU32(2) + buildServer(b"\x01\x02\x03\x04", 4661),
    b"\xe0" + toU32(1) + buildServer(b"\x01\x02\x03\x04", 4661)[:-1],
])
def test_parse_rejects_broken_server_met(data):
    with pytest.raises(ValueError):
        parseServerList(data)

