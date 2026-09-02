from os.path import join

from pythonforandroid.recipe import Recipe
from pythonforandroid.logger import info, error


class Gd3qjsRecipe(Recipe):
    version = "0.15.1"
    url = None

    PREBUILT_DIR = "/opt/gd3-qjs"
    BINARIES = ("libqjs.so",)

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
                error(f"[gd3qjs] 预置二进制缺失: {lib}（检查 Dockerfile 编译步骤）")
                raise FileNotFoundError(lib)
        info(f"[gd3qjs] install_libs 预编 qjs -> lib/{arch.arch}/")
        self.install_libs(arch, *libs)

recipe = Gd3qjsRecipe()
