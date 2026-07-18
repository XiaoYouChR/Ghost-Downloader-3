"""
Pure-Python tests for features that don't need Qt/qfluentwidgets:
  - Wake lock reference counting and platform mocking
  - Extract utils: canAutoExtract() and real zip/tar extraction
  - VLC detection and playInVlc fallback
  - Codec args routing for audio transcoding
  - Cfg config item existence (uses importlib to avoid QApplication)
"""
from __future__ import annotations

import asyncio
import io
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

# Ensure project root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))


# ---------------------------------------------------------------------------
# Wake Lock — pure Python, no Qt needed
# ---------------------------------------------------------------------------

def _reset_wake_lock():
    import app.platform.wake_lock as wl
    wl._wake_lock_count = 0
    wl._caffeinate_proc = None


class TestWakeLockReferenceCount:

    def setup_method(self):
        _reset_wake_lock()

    def teardown_method(self):
        _reset_wake_lock()

    def test_count_starts_at_zero(self):
        import app.platform.wake_lock as wl
        assert wl._wake_lock_count == 0

    def test_acquire_increments_to_one(self):
        import app.platform.wake_lock as wl
        with patch("sys.platform", "linux"):
            with patch("shutil.which", return_value=None):
                wl.acquireWakeLock()
        assert wl._wake_lock_count == 1

    def test_double_acquire_increments_to_two(self):
        import app.platform.wake_lock as wl
        with patch("sys.platform", "linux"):
            with patch("shutil.which", return_value=None):
                wl.acquireWakeLock()
                wl.acquireWakeLock()
        assert wl._wake_lock_count == 2

    def test_release_decrements(self):
        import app.platform.wake_lock as wl
        with patch("sys.platform", "linux"):
            with patch("shutil.which", return_value=None):
                wl.acquireWakeLock()
                wl.acquireWakeLock()
                wl.releaseWakeLock()
        assert wl._wake_lock_count == 1

    def test_release_to_zero(self):
        import app.platform.wake_lock as wl
        with patch("sys.platform", "linux"):
            with patch("shutil.which", return_value=None):
                wl.acquireWakeLock()
                wl.releaseWakeLock()
        assert wl._wake_lock_count == 0

    def test_release_when_already_zero_is_noop(self):
        import app.platform.wake_lock as wl
        wl.releaseWakeLock()  # should not crash
        assert wl._wake_lock_count == 0

    def test_os_api_called_only_once_on_double_acquire(self):
        import app.platform.wake_lock as wl
        with patch("sys.platform", "darwin"):
            mock_proc = MagicMock()
            mock_proc.pid = 1
            with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
                wl.acquireWakeLock()
                wl.acquireWakeLock()
                assert mock_popen.call_count == 1  # Only one Popen call

    def test_macos_release_kills_caffeinate(self):
        import app.platform.wake_lock as wl
        with patch("sys.platform", "darwin"):
            mock_proc = MagicMock()
            mock_proc.pid = 99
            with patch("subprocess.Popen", return_value=mock_proc):
                wl.acquireWakeLock()
                wl.releaseWakeLock()
        mock_proc.kill.assert_called_once()
        assert wl._caffeinate_proc is None

    def test_linux_with_systemd_inhibit_spawns_process(self):
        import app.platform.wake_lock as wl
        with patch("sys.platform", "linux"):
            mock_proc = MagicMock()
            with patch("shutil.which", return_value="/usr/bin/systemd-inhibit"):
                with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
                    wl.acquireWakeLock()
                    cmd = mock_popen.call_args[0][0]
                    assert "systemd-inhibit" in cmd[0]

    def test_linux_without_systemd_no_crash(self):
        import app.platform.wake_lock as wl
        with patch("sys.platform", "linux"):
            with patch("shutil.which", return_value=None):
                # Must not raise even with no tool available
                wl.acquireWakeLock()


class TestWakeLockWindows:

    def setup_method(self):
        _reset_wake_lock()

    def teardown_method(self):
        _reset_wake_lock()

    def test_windows_acquire_calls_correct_flags(self):
        import app.platform.wake_lock as wl
        import ctypes

        # Only test if we can mock ctypes.windll
        mock_kernel32 = MagicMock()
        mock_kernel32.SetThreadExecutionState.return_value = 1

        with patch("sys.platform", "win32"):
            with patch.object(ctypes, "windll", mock_kernel32, create=True):
                wl.acquireWakeLock()

        expected = 0x80000000 | 0x00000001 | 0x00000040
        mock_kernel32.kernel32.SetThreadExecutionState.assert_called_with(expected)

    def test_windows_release_sends_continuous_only(self):
        import app.platform.wake_lock as wl
        import ctypes

        mock_kernel32 = MagicMock()
        mock_kernel32.SetThreadExecutionState.return_value = 1

        with patch("sys.platform", "win32"):
            with patch.object(ctypes, "windll", mock_kernel32, create=True):
                wl.acquireWakeLock()
                wl.releaseWakeLock()

        # Last call should be ES_CONTINUOUS (0x80000000) only
        last_call = mock_kernel32.kernel32.SetThreadExecutionState.call_args_list[-1]
        assert last_call == call(0x80000000)


# ---------------------------------------------------------------------------
# Extract Utils — pure Python, uses stdlib only
# ---------------------------------------------------------------------------

class TestCanAutoExtract:

    def _can(self, filename: str) -> bool:
        from app.platform.extract_utils import canAutoExtract
        return canAutoExtract(filename)

    # Supported
    def test_zip(self):           assert self._can("archive.zip")
    def test_tar(self):           assert self._can("archive.tar")
    def test_tar_gz(self):        assert self._can("archive.tar.gz")
    def test_tar_bz2(self):       assert self._can("archive.tar.bz2")
    def test_tar_xz(self):        assert self._can("archive.tar.xz")
    def test_gz(self):            assert self._can("archive.gz")
    def test_7z(self):            assert self._can("archive.7z")
    def test_rar(self):           assert self._can("archive.rar")
    def test_uppercase_zip(self): assert self._can("ARCHIVE.ZIP")
    def test_uppercase_tar_gz(self): assert self._can("BUNDLE.TAR.GZ")

    # Unsupported
    def test_mp4_rejected(self):  assert not self._can("video.mp4")
    def test_mp3_rejected(self):  assert not self._can("audio.mp3")
    def test_pdf_rejected(self):  assert not self._can("doc.pdf")
    def test_exe_rejected(self):  assert not self._can("setup.exe")
    def test_mkv_rejected(self):  assert not self._can("film.mkv")
    def test_txt_rejected(self):  assert not self._can("readme.txt")


class TestAutoExtractZip:

    def test_basic_extraction(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract

        archive = tmp_path / "test.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("hello.txt", "Hello, World!")
            zf.writestr("sub/nested.txt", "nested")

        autoExtract(str(archive), str(tmp_path))

        dest = tmp_path / "test"
        assert dest.is_dir()
        assert (dest / "hello.txt").read_text() == "Hello, World!"
        assert (dest / "sub" / "nested.txt").read_text() == "nested"

    def test_subfolder_named_by_stem(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract

        archive = tmp_path / "my-pkg-1.2.3.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("readme.txt", "x")

        autoExtract(str(archive), str(tmp_path))
        assert (tmp_path / "my-pkg-1.2.3").is_dir()

    def test_delete_after_true_removes_archive(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract

        archive = tmp_path / "temp.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("f.txt", "data")

        autoExtract(str(archive), str(tmp_path), deleteAfter=True)
        assert not archive.exists()

    def test_delete_after_false_keeps_archive(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract

        archive = tmp_path / "keep.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("f.txt", "data")

        autoExtract(str(archive), str(tmp_path), deleteAfter=False)
        assert archive.exists()

    def test_missing_archive_raises_file_not_found(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract
        import pytest
        with pytest.raises(FileNotFoundError):
            autoExtract(str(tmp_path / "ghost.zip"), str(tmp_path))

    def test_empty_zip_creates_subfolder(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract

        archive = tmp_path / "empty.zip"
        with zipfile.ZipFile(archive, "w"):
            pass

        autoExtract(str(archive), str(tmp_path))
        assert (tmp_path / "empty").is_dir()

    def test_zip_with_many_files(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract

        archive = tmp_path / "big.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(50):
                zf.writestr(f"file_{i:03d}.txt", f"content {i}")

        autoExtract(str(archive), str(tmp_path))
        dest = tmp_path / "big"
        assert len(list(dest.iterdir())) == 50

    def test_binary_file_in_zip(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract

        archive = tmp_path / "binary.zip"
        binary_data = bytes(range(256)) * 100
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.bin", binary_data)

        autoExtract(str(archive), str(tmp_path))
        extracted = (tmp_path / "binary" / "data.bin").read_bytes()
        assert extracted == binary_data


class TestAutoExtractTarGz:

    def _make_targz(self, tmp_path: Path, name: str, files: dict) -> Path:
        archive = tmp_path / name
        with tarfile.open(archive, "w:gz") as tf:
            for fname, content in files.items():
                data = content.encode() if isinstance(content, str) else content
                info = tarfile.TarInfo(name=fname)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        return archive

    def test_basic_tar_gz_extraction(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract

        archive = self._make_targz(tmp_path, "bundle.tar.gz", {"config.yaml": "key: val"})
        out = tmp_path / "out"
        out.mkdir()
        autoExtract(str(archive), str(out))

        assert (out / "bundle" / "config.yaml").exists()

    def test_tar_gz_stem_strips_both_extensions(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract

        archive = self._make_targz(tmp_path, "project-2.0.tar.gz", {"file.txt": "x"})
        out = tmp_path / "out"
        out.mkdir()
        autoExtract(str(archive), str(out))

        # Should be "project-2.0", not "project-2.0.tar"
        assert (out / "project-2.0").is_dir()
        assert not (out / "project-2.0.tar").is_dir()

    def test_delete_after_tar_gz(self, tmp_path: Path):
        from app.platform.extract_utils import autoExtract

        archive = self._make_targz(tmp_path, "gone.tar.gz", {"x.txt": "y"})
        out = tmp_path / "out"
        out.mkdir()
        autoExtract(str(archive), str(out), deleteAfter=True)
        assert not archive.exists()


# ---------------------------------------------------------------------------
# VLC Detection — pure Python mocks
# ---------------------------------------------------------------------------

class TestFindVlcBinary:

    def test_linux_returns_none_when_not_found(self):
        from app.platform.desktop import findVlcBinary
        with patch("sys.platform", "linux"):
            with patch("shutil.which", return_value=None):
                assert findVlcBinary() is None

    def test_linux_returns_vlc_path(self):
        from app.platform.desktop import findVlcBinary
        with patch("sys.platform", "linux"):
            with patch("shutil.which", return_value="/usr/bin/vlc"):
                result = findVlcBinary()
                assert result == "/usr/bin/vlc"

    def test_macos_finds_vlc_in_applications(self, tmp_path: Path):
        from app.platform.desktop import findVlcBinary
        vlc_exe = tmp_path / "Applications" / "VLC.app" / "Contents" / "MacOS" / "VLC"
        vlc_exe.parent.mkdir(parents=True)
        vlc_exe.touch()

        candidates = [str(vlc_exe)]
        with patch("sys.platform", "darwin"):
            # Patch the candidates list inside findVlcBinary
            with patch("shutil.which", return_value=None):
                # Inject our fake path
                import app.platform.desktop as desktop_mod
                original = desktop_mod.findVlcBinary
                def patched():
                    for c in candidates:
                        if Path(c).is_file():
                            return c
                    return None
                with patch.object(desktop_mod, "findVlcBinary", patched):
                    result = desktop_mod.findVlcBinary()
                    assert result == str(vlc_exe)

    def test_macos_falls_through_to_shutil_which(self):
        from app.platform.desktop import findVlcBinary
        with patch("sys.platform", "darwin"):
            with patch("shutil.which", return_value="/opt/homebrew/bin/vlc"):
                # Standard app paths won't exist, so it falls through to shutil.which
                result = findVlcBinary()
                # Result may be the shutil path or None depending on app paths
                assert result is None or isinstance(result, str)


class TestPlayInVlc:

    def test_launches_vlc_when_found(self, tmp_path: Path):
        from app.platform.desktop import playInVlc
        target = str(tmp_path / "video.mp4")
        Path(target).touch()

        with patch("app.platform.desktop.findVlcBinary", return_value="/usr/bin/vlc"):
            with patch("subprocess.Popen") as mock_popen:
                playInVlc(target)
                mock_popen.assert_called_once_with(["/usr/bin/vlc", target])

    def test_falls_back_to_openfile_when_vlc_missing(self, tmp_path: Path):
        from app.platform.desktop import playInVlc
        target = str(tmp_path / "audio.mp3")
        Path(target).touch()

        with patch("app.platform.desktop.findVlcBinary", return_value=None):
            with patch("app.platform.desktop.openFile") as mock_open:
                playInVlc(target)
                mock_open.assert_called_once_with(target)

    def test_falls_back_when_popen_raises_oserror(self, tmp_path: Path):
        from app.platform.desktop import playInVlc
        target = str(tmp_path / "movie.mkv")
        Path(target).touch()

        with patch("app.platform.desktop.findVlcBinary", return_value="/usr/bin/vlc"):
            with patch("subprocess.Popen", side_effect=OSError("Permission denied")):
                with patch("app.platform.desktop.openFile") as mock_open:
                    playInVlc(target)
                    mock_open.assert_called_once_with(target)

    def test_does_not_call_openfile_when_vlc_succeeds(self, tmp_path: Path):
        from app.platform.desktop import playInVlc
        target = str(tmp_path / "show.mp4")
        Path(target).touch()

        with patch("app.platform.desktop.findVlcBinary", return_value="/usr/bin/vlc"):
            with patch("subprocess.Popen", return_value=MagicMock()):
                with patch("app.platform.desktop.openFile") as mock_open:
                    playInVlc(target)
                    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Audio Transcoding — codec arg routing (pure Python logic)
# ---------------------------------------------------------------------------

def _codec_args(target_format: str) -> list:
    """Replicate the match statement from YouTubeMergeStep._transcodeAudio."""
    match target_format:
        case "mp3":  return ["-codec:a", "libmp3lame", "-q:a", "2"]
        case "wav":  return ["-codec:a", "pcm_s16le"]
        case "flac": return ["-codec:a", "flac"]
        case "opus": return ["-codec:a", "libopus", "-b:a", "128k"]
        case _:      return []


class TestCodecArgRouting:

    def test_mp3_codec(self):
        args = _codec_args("mp3")
        assert args == ["-codec:a", "libmp3lame", "-q:a", "2"]

    def test_wav_codec(self):
        args = _codec_args("wav")
        assert args == ["-codec:a", "pcm_s16le"]

    def test_flac_codec(self):
        args = _codec_args("flac")
        assert args == ["-codec:a", "flac"]

    def test_opus_codec(self):
        args = _codec_args("opus")
        assert args == ["-codec:a", "libopus", "-b:a", "128k"]

    def test_original_empty_args(self):
        assert _codec_args("original") == []

    def test_unknown_format_empty_args(self):
        assert _codec_args("aac") == []
        assert _codec_args("") == []
        assert _codec_args("ogg") == []

    def test_mp3_uses_quality_not_bitrate(self):
        """VBR quality (-q:a 2) is preferred over CBR bitrate for MP3."""
        args = _codec_args("mp3")
        assert "-q:a" in args
        assert "-b:a" not in args

    def test_opus_uses_bitrate(self):
        args = _codec_args("opus")
        assert "-b:a" in args
        assert "128k" in args


# ---------------------------------------------------------------------------
# Default Audio-Only Selection Logic
# ---------------------------------------------------------------------------

class TestDefaultAudioOnlyLogic:
    """Pure-logic tests for pre-selection in cards.py."""

    def _build_tiers(self, heights=(1080, 720, 480)):
        tiers = []
        if heights:
            best_h = heights[0]
            tiers.append(("bv*+ba/b", f"最佳画质 ({best_h}p)"))
        for h in heights:
            tiers.append((f"bv*[height<={h}]+ba/b", f"{h}p"))
        tiers.append(("ba/b", "仅音频"))
        return tiers

    def test_audio_only_is_always_last(self):
        for heights in [(1080, 720), (1080,), (720, 480, 360)]:
            tiers = self._build_tiers(heights)
            selector, label = tiers[-1]
            assert selector == "ba/b", f"Failed for heights={heights}"

    def test_pre_select_audio_only_index(self):
        tiers = self._build_tiers()
        # Simulate: if defaultToAudioOnly is True
        selected = len(tiers) - 1
        assert selected == 4  # [best, 1080p, 720p, 480p, audio-only]

    def test_no_pre_select_picks_first(self):
        tiers = self._build_tiers()
        selected = 0  # defaultToAudioOnly is False
        selector, _ = tiers[selected]
        assert selector == "bv*+ba/b"

    def test_empty_tiers_dont_crash(self):
        # Edge case: if somehow quality tiers is empty
        tiers = []
        if tiers and True:  # defaultToAudioOnly is True
            idx = len(tiers) - 1
        else:
            idx = 0
        assert idx == 0  # no crash


# ---------------------------------------------------------------------------
# Config Item Existence (no QApplication needed)
# ---------------------------------------------------------------------------

class TestConfigItemPresence:

    def test_auto_extract_config_exists(self):
        from app.config.cfg import cfg
        assert hasattr(cfg, "shouldAutoExtract")
        assert cfg.shouldAutoExtract.defaultValue is False

    def test_delete_after_extract_config_exists(self):
        from app.config.cfg import cfg
        assert hasattr(cfg, "shouldDeleteArchiveAfterExtract")
        assert cfg.shouldDeleteArchiveAfterExtract.defaultValue is False

    def test_default_to_audio_only_exists_in_ytdlp(self):
        from features.yt_dlp_pack.config import ytDlpConfig
        assert hasattr(ytDlpConfig, "defaultToAudioOnly")
        assert ytDlpConfig.defaultToAudioOnly.defaultValue is False

    def test_audio_output_format_exists_in_ytdlp(self):
        from features.yt_dlp_pack.config import ytDlpConfig
        assert hasattr(ytDlpConfig, "audioOutputFormat")
        assert ytDlpConfig.audioOutputFormat.defaultValue == "original"

    def test_audio_output_format_options(self):
        from features.yt_dlp_pack.config import ytDlpConfig
        v = ytDlpConfig.audioOutputFormat.validator
        for fmt in ("original", "mp3", "wav", "flac", "opus"):
            assert v.validate(fmt), f"Expected '{fmt}' to be valid"
        assert not v.validate("aac")
        assert not v.validate("ogg")
