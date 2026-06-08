"""gd3ffmpeg —— 把镜像预置的 bionic arm64 ffmpeg/ffprobe 二进制 install_libs 进 APK。

二进制来源 hzw1199/Android-FFmpeg-Prebuilt 8.1.1(NDK r28c、含 MediaCodec 硬解), 已改名 lib*.so
(Android 只释放 lib/ 下 lib*.so 到 nativeLibraryDir)。url=None: 无外部源, 由 Dockerfile 预置。
"""

from os.path import join

from pythonforandroid.recipe import Recipe
from pythonforandroid.logger import info, error


class Gd3ffmpegRecipe(Recipe):
    version = "8.1.1"
    url = None

    # Dockerfile 预置目录
    PREBUILT_DIR = "/opt/gd3-ffmpeg"
    BINARIES = ("libffmpeg.so", "libffprobe.so", "libnm3u8dlre.so")

    def should_build(self, arch):
        return True

    def prepare_build_dir(self, arch):
        from pythonforandroid.util import ensure_dir
        ensure_dir(self.get_build_dir(arch))

    def unpack(self, arch):
        pass

    def build_arch(self, arch):
        from os.path import exists
        libs = [join(self.PREBUILT_DIR, b) for b in self.BINARIES]
        for lib in libs:
            if not exists(lib):
                error(f"[gd3ffmpeg] 预置二进制缺失: {lib}（检查 Dockerfile 下载步骤）")
                raise FileNotFoundError(lib)
        info(f"[gd3ffmpeg] install_libs 预编 ffmpeg/ffprobe -> lib/{arch.arch}/")
        self.install_libs(arch, *libs)


recipe = Gd3ffmpegRecipe()
