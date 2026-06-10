from app.bases.categories import categoryFolderFor


def test_videoGoesToVideoSubfolder():
    assert categoryFolderFor("movie.mp4", "/dl") == "/dl/Video"


def test_audioGoesToAudioSubfolder():
    assert categoryFolderFor("song.mp3", "/dl") == "/dl/Audio"


def test_doubleExtensionArchive():
    # tar.gz 走双后缀匹配，归到压缩包
    assert categoryFolderFor("backup.tar.gz", "/dl") == "/dl/Archives"


def test_unknownExtensionStaysInBase():
    assert categoryFolderFor("mystery.xyz", "/dl") == "/dl"


def test_noExtensionStaysInBase():
    assert categoryFolderFor("README", "/dl") == "/dl"
