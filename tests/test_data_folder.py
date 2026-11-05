from __future__ import annotations

from app.config.data_folder import PathSerializer


def relocate(value, oldFolder, newFolder):
    return PathSerializer(newFolder).deserialize(PathSerializer(oldFolder).serialize(value))


def test_move_keeps_path_inside(tmp_path):
    oldFolder = tmp_path / "old" / "GhostDownloader"
    newFolder = tmp_path / "new" / "GhostDownloader"

    assert relocate(f"{oldFolder}/FFmpeg", oldFolder, newFolder) == (newFolder / "FFmpeg").as_posix()
    assert relocate(str(oldFolder), oldFolder, newFolder) == newFolder.as_posix()


def test_move_keeps_path_outside_unchanged(tmp_path):
    oldFolder = tmp_path / "old" / "GhostDownloader"
    outside = (tmp_path / "Movies").as_posix()

    assert relocate(outside, oldFolder, tmp_path / "new" / "GhostDownloader") == outside
    assert relocate("", oldFolder, tmp_path / "new" / "GhostDownloader") == ""


def test_move_keeps_each_recent_folder(tmp_path):
    oldFolder = tmp_path / "old" / "GhostDownloader"
    newFolder = tmp_path / "new" / "GhostDownloader"
    outside = (tmp_path / "Movies").as_posix()

    assert relocate([f"{oldFolder}/Saved", outside], oldFolder, newFolder) == [
        (newFolder / "Saved").as_posix(), outside,
    ]


def test_load_repairs_stale_path_when_moved_copy_exists(tmp_path):
    newFolder = tmp_path / "new" / "GhostDownloader"
    (newFolder / "FFmpeg").mkdir(parents=True)
    stale = (tmp_path / "old" / "GhostDownloader" / "FFmpeg").as_posix()

    assert PathSerializer(newFolder).deserialize(stale) == (newFolder / "FFmpeg").as_posix()


def test_load_keeps_stale_path_without_moved_copy(tmp_path):
    newFolder = tmp_path / "new" / "GhostDownloader"
    newFolder.mkdir(parents=True)
    stale = (tmp_path / "old" / "GhostDownloader" / "FFmpeg").as_posix()

    assert PathSerializer(newFolder).deserialize(stale) == stale
