from app.protocol.framing import Unframer, frame


def test_unframer_yieldsCompleteFrames():
    unframer = Unframer()
    stream = frame(b"hello") + frame(b"world")

    assert unframer.feed(stream) == [b"hello", b"world"]


def test_unframer_handlesSplitAcrossChunks():
    unframer = Unframer()
    one, two = frame(b"hello"), frame(b"world")

    assert unframer.feed(one[:3]) == []
    assert unframer.feed(one[3:] + two[:2]) == [b"hello"]
    assert unframer.feed(two[2:]) == [b"world"]


def test_unframer_emptyUntilLengthKnown():
    unframer = Unframer()
    payload = frame(b"abcd")

    assert unframer.feed(payload[:2]) == []
    assert unframer.feed(payload[2:]) == [b"abcd"]
