import os
from glob import glob
from os.path import join

from pythonforandroid.recipe import RustCompiledComponentsRecipe


class WreqRecipe(RustCompiledComponentsRecipe):
    version = "0.12.0"
    url = "https://files.pythonhosted.org/packages/source/w/wreq/wreq-{version}.tar.gz"
    site_packages_name = "wreq"

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        llvm = self.ctx.ndk.llvm_prebuilt_dir
        clang_include = glob(join(llvm, "lib", "clang", "*", "include"))[0]

        # maturin 隔离子进程不继承镜像 ENV, 显式喂 rustup 并强制 toolchain(绕开"无默认")
        env["RUSTUP_HOME"] = os.environ.get("RUSTUP_HOME", "/opt/rustup")
        env["RUSTUP_TOOLCHAIN"] = "stable"
        # 镜像的 /opt/cargo 是 root 只读, builder 下载 crate 写不进; 用可写的 home cargo
        env["CARGO_HOME"] = join(os.path.expanduser("~"), ".cargo")
        # android 目标过不了 auditwheel(非 manylinux), 跳过(同上游 CI)
        env["MATURIN_PEP517_ARGS"] = "--skip-auditwheel"
        # btls-sys 0.5.6 编 BoringSSL 走 NDK 的 cmake toolchain, 需要这个指路
        env["ANDROID_NDK_HOME"] = self.ctx.ndk_dir
        # 镜像自带 cmake 3.25 在 NDK toolchain 下 FindThreads 会失败, 用隔离的 cmake>=4
        env["CMAKE"] = "/opt/cmake4/bin/cmake"
        # bindgen 给 BoringSSL 生成绑定, libclang 在 NDK 的 musl/lib 下
        env["LIBCLANG_PATH"] = join(llvm, "musl", "lib")
        env["BINDGEN_EXTRA_CLANG_ARGS"] = (
            f"--target=aarch64-linux-android{self.ctx.ndk_api} "
            f"--sysroot={self.ctx.ndk.sysroot} -isystem {clang_include}"
        )
        env["PATH"] = join(llvm, "bin") + ":" + env["PATH"]
        return env


recipe = WreqRecipe()
