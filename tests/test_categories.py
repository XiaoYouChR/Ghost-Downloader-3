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


def test_customRulesOverrideDefaults():
    # 给定自定义规则就用它（同 presets 结构），默认集让位
    rules = [{"extensions": ["xyz"], "folder": "{default}/Custom"}]
    assert categoryFolderFor("file.xyz", "/dl", rules) == "/dl/Custom"
    assert categoryFolderFor("movie.mp4", "/dl", rules) == "/dl"  # mp4 不在自定义规则里 → 兜底
