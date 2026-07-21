# QuickJS-NG on Android from a Python (PySide6) App

Research date: 2026-07-05

---

## 1. Does QuickJS-NG provide prebuilt Android arm64 binaries?

**No.** The latest release (v0.15.1, 2026-06-04) ships 19 assets, none
Android-specific:

```
qjs-darwin, qjsc-darwin
qjs-linux-{aarch64,armv7,riscv64,x86,x86_64}
qjsc-linux-{aarch64,armv7,riscv64,x86,x86_64}
qjs-windows-{x86,x86_64}.exe, qjsc-windows-{x86,x86_64}.exe
qjs-wasi.wasm, qjs-wasi-reactor.wasm
quickjs-amalgam.zip
```

Source: [GitHub Releases v0.15.1](https://github.com/quickjs-ng/quickjs/releases/tag/v0.15.1)

### CI has an Android build job (not published)

`.github/workflows/ci.yml` contains an `android` job that builds `qjs` for
`arm64-v8a` (API 24) using NDK 26 via the `reactnativecommunity/react-native-android:v13.0`
container. The exact commands:

```bash
cmake -B build \
  -DCMAKE_TOOLCHAIN_FILE=$ANDROID_HOME/ndk/26.0.10792818/build/cmake/android.toolchain.cmake \
  -DCMAKE_BUILD_TYPE=Release \
  -DANDROID_ABI="arm64-v8a" \
  -DANDROID_PLATFORM=android-24 \
  -DQJS_BUILD_LIBC=ON \
  ..
cmake --build build --target qjs
```

This artifact is **not** included in `release.yml` -- Android is CI-only.

Source: [ci.yml](https://github.com/quickjs-ng/quickjs/blob/master/.github/workflows/ci.yml),
[release.yml](https://github.com/quickjs-ng/quickjs/blob/master/.github/workflows/release.yml)

### The Linux aarch64 static binary already works on Android

Issue [#1512](https://github.com/quickjs-ng/quickjs/issues/1512) confirms
that the `qjs-linux-aarch64` static binary from releases works on Android
for basic JS evaluation. The only caveat: `popen()` returns NULL because
musl hardcodes `/bin/sh` instead of `/system/bin/sh`. This is irrelevant
for yt-dlp's use case (it passes JS via temp files and reads stdout, never
uses `popen`).

### Known Android issues

| Issue | Status | Summary |
|-------|--------|---------|
| [#1512](https://github.com/quickjs-ng/quickjs/issues/1512) | Open | `popen()` NULL on Android (musl `/bin/sh` path). Native NDK build avoids this. |
| [#304](https://github.com/quickjs-ng/quickjs/issues/304) | Closed | `dlmalloc` not found -- fixed by removing Android-specific allocator code. |

### CMakeLists.txt supports shared library builds

```cmake
xoption(BUILD_SHARED_LIBS "Build a shared library" OFF)
```

When ON, produces `libqjs.so` with SOVERSION. This is relevant for both
the nativeLibraryDir bundling approach and potential ctypes/cffi loading.

Source: [CMakeLists.txt](https://github.com/quickjs-ng/quickjs/blob/master/CMakeLists.txt)

---

## 2. Can a Python app on Android execute a native binary via subprocess?

### The W^X problem

Android 10+ (API 29+) enforces W^X: files outside the APK's
`nativeLibraryDir` cannot be `exec()`'d. Two solutions exist:

### Solution A: nativeLibraryDir bundling (recommended)

Files in `nativeLibraryDir` have execute permission on Android 10+. The
W^X restriction only applies to app data dirs like
`/data/data/pkg/files/`. A binary bundled in the APK as a native library
is unpacked to `nativeLibraryDir` and can be executed directly -- **no
linker64 hack needed**.

Requirements:
- Binary must be renamed with `lib` prefix and `.so` suffix (e.g.
  `qjs` -> `libqjs.so`) to satisfy Android's native library packaging rules
- Must be placed in `jniLibs/{arch}/` or installed via p4a recipe's
  `install_libs()`

This is the **proven pattern** used by:
- **This project** (`gd3ffmpeg` recipe): bundles `libffmpeg.so`,
  `libffprobe.so`, `libnm3u8dlre.so` via `install_libs()`.
  Source: [`android/recipes/gd3ffmpeg/__init__.py`](/Users/xiaoyouchr/PycharmProjects/Ghost-Downloader-3/android/recipes/gd3ffmpeg/__init__.py)
- **youtubedl-android** (v0.18.1, PR [#338](https://github.com/yausername/youtubedl-android/pull/338)):
  bundles `libqjs.so` in `jniLibs/{arm64-v8a,armeabi-v7a,x86,x86_64}/`.
  Binary source: extracted from Termux packages (~900 KB per arch).

### Solution B: linker64 (for runtime-downloaded binaries only)

ADR-0005 documents the validated workaround for binaries that are
downloaded at runtime (not bundled in the APK):

```
/system/bin/linker64 <path-to-binary> [args...]
```

This bypasses SELinux exec restrictions. Currently used for N_m3u8DL-RE.

Source: [`docs/adr/0005-android-native-binary-exec-via-linker64.md`](/Users/xiaoyouchr/PycharmProjects/Ghost-Downloader-3/docs/adr/0005-android-native-binary-exec-via-linker64.md)

**For qjs, Solution A is clearly better** -- the binary is small (~900 KB),
doesn't update independently of the app, and nativeLibraryDir is the
system-blessed execution path.

---

## 3. Python bindings for QuickJS (in-process alternative)

| Package | Engine | Mechanism | Android arm64? | Notes |
|---------|--------|-----------|----------------|-------|
| [`quickjs`](https://pypi.org/project/quickjs/) 1.19.4 | Original QuickJS (bellard, archived) | C extension | **No** -- x86_64 desktop only | Dead upstream, no longer maintained |
| [`quickjs-ng`](https://pypi.org/project/quickjs-ng/) 0.15.1.1 | QuickJS-NG | C extension | **No** -- has linux_aarch64 (manylinux) but not Android | Drop-in replacement. [genotrance/quickjs-ng](https://github.com/genotrance/quickjs-ng). Uses submodule + `module.c` binding. |
| [`quickjs-rs`](https://pypi.org/project/quickjs-rs/) | QuickJS-NG via WASM | wasmtime sandbox | **Possible** -- pure Python wheel + wasmtime has Android ARM64 wheels (`wasmtime-46.0.1-py3-none-android_26_arm64_v8a.whl`) | Requires Python 3.11+. wasmtime on Android is "less well tested". |
| [`py-mini-racer`](https://pypi.org/project/mini-racer/) | V8 | C extension | **No** | V8 is too heavy for this use case |
| [`ytdlp-jsc`](https://pypi.org/project/ytdlp-jsc/) 0.1.7 | QuickJS (Rust, PyO3) | Rust C extension via maturin | **No** -- has `manylinux_2_39_aarch64` but not Android | yt-dlp plugin; embeds QuickJS+SWC in-process. 1.44x slower than CLI but eliminates subprocess startup. |

### quickjs-rs + wasmtime: the most promising in-process path

`quickjs-rs` (by LangChain) is a pure Python wheel (`py3-none-any`). It
compiles QuickJS-NG to WASM and runs it inside `wasmtime`. Since
`wasmtime` publishes Android ARM64 wheels, the full chain could work on
Android in-process.

**Concerns:**
- wasmtime adds ~15 MB to the APK
- wasmtime on Android is described as "less well tested" by the project
- Performance overhead of WASM interpretation vs native binary
- Requires Python 3.11+ (this project already uses 3.11)
- Not proven in production on Android

Source: [PyPI quickjs-rs](https://pypi.org/project/quickjs-rs/),
[PyPI wasmtime](https://pypi.org/project/wasmtime/)

### Could quickjs-ng (Python) be cross-compiled for Android?

Yes, in theory. It's a single C extension (`module.c`) wrapping QuickJS-NG
source (included as submodule). A p4a recipe could cross-compile it with
NDK, giving in-process `import quickjs; ctx = quickjs.Context(); ctx.eval(...)`.

**But this doesn't help with yt-dlp**: yt-dlp's EJS system invokes JS
runtimes exclusively via subprocess. Using an in-process engine would
require either monkey-patching yt-dlp's JS runtime discovery or writing a
yt-dlp plugin (like `ytdlp-jsc`).

---

## 4. Building QuickJS-NG for Android

### Difficulty: trivial

QuickJS-NG is pure C11, uses CMake, and the project's own CI already has a
working Android arm64 build. Cross-compilation requires only the NDK
toolchain file:

```bash
cmake -B build \
  -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
  -DCMAKE_BUILD_TYPE=Release \
  -DANDROID_ABI="arm64-v8a" \
  -DANDROID_PLATFORM=android-28 \
  -DQJS_BUILD_LIBC=ON \
  .
cmake --build build --target qjs
```

The resulting `qjs` binary is ~1-2 MB. For nativeLibraryDir bundling, it
must be renamed to `libqjs.so`.

### As a shared library

Add `-DBUILD_SHARED_LIBS=ON` to produce `libqjs.so` (the engine library,
not the CLI binary). This could be loaded via `ctypes`/`cffi` from Python,
but writing a Python wrapper around the QuickJS C API is significant work
and not needed when the CLI binary approach works.

### Proposed gd3qjs p4a recipe

Following the `gd3ffmpeg` recipe pattern
([`android/recipes/gd3ffmpeg/__init__.py`](/Users/xiaoyouchr/PycharmProjects/Ghost-Downloader-3/android/recipes/gd3ffmpeg/__init__.py)),
a `gd3qjs` recipe would:

1. **Dockerfile step**: cross-compile `qjs` with NDK in the Docker build
   image, stage it at `/opt/gd3-qjs/libqjs.so`
2. **Recipe**: copy the pre-built binary into nativeLibraryDir via
   `install_libs()`

```python
# android/recipes/gd3qjs/__init__.py
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
                error(f"[gd3qjs] missing: {lib}")
                raise FileNotFoundError(lib)
        info(f"[gd3qjs] install_libs qjs -> lib/{arch.arch}/")
        self.install_libs(arch, *libs)

recipe = Gd3qjsRecipe()
```

Dockerfile addition:

```dockerfile
ARG QJS_VERSION=v0.15.1
RUN git clone --depth 1 -b ${QJS_VERSION} https://github.com/quickjs-ng/quickjs.git /tmp/quickjs \
    && cd /tmp/quickjs \
    && cmake -B build \
        -DCMAKE_TOOLCHAIN_FILE=$ANDROID_HOME/ndk/*/build/cmake/android.toolchain.cmake \
        -DCMAKE_BUILD_TYPE=Release \
        -DANDROID_ABI="arm64-v8a" \
        -DANDROID_PLATFORM=android-28 \
        -DQJS_BUILD_LIBC=ON \
        . \
    && cmake --build build --target qjs \
    && mkdir -p /opt/gd3-qjs \
    && cp build/qjs /opt/gd3-qjs/libqjs.so \
    && chmod a+rx /opt/gd3-qjs/libqjs.so \
    && file /opt/gd3-qjs/libqjs.so | grep -q "ARM aarch64" && echo "[qjs] arm64 OK" \
    && rm -rf /tmp/quickjs
```

---

## 5. How does yt-dlp handle QuickJS on Android?

### yt-dlp itself: no Android-specific code

yt-dlp invokes JS runtimes exclusively via **subprocess**. The relevant
source files:

- `yt_dlp/utils/_jsruntime.py` -- `QuickJsRuntime` discovers `qjs`,
  detects version, distinguishes QuickJS vs QuickJS-NG
- `yt_dlp/extractor/youtube/jsc/_builtin/quickjs.py` -- `QuickJSJCP`
  subprocess execution, temp file writes

Runtime discovery: `shutil.which('qjs')` for PATH lookup, or explicit
`--js-runtimes quickjs:/path/to/qjs`.

Minimum QuickJS version: `2023-12-09`. Versions before `2025-04-26` have a
performance warning.

Source: [yt-dlp EJS wiki](https://github.com/yt-dlp/yt-dlp/wiki/EJS),
[yt-dlp source](https://github.com/yt-dlp/yt-dlp)

### youtubedl-android: the proven Android solution

[youtubedl-android](https://github.com/yausername/youtubedl-android) v0.18.1
(PR [#338](https://github.com/yausername/youtubedl-android/pull/338),
merged 2025-11-16) added QuickJS support for Android:

1. `qjs` binary renamed to `libqjs.so` (`lib` prefix + `.so` suffix)
2. Bundled in `library/src/main/jniLibs/{arm64-v8a,armeabi-v7a,x86,x86_64}/`
3. Android unpacks to `nativeLibraryDir` at install time
4. Executed as subprocess from `nativeLibraryDir` -- no linker64 needed
5. yt-dlp configured with `--js-runtimes quickjs:<nativeLibraryDir>/libqjs.so`
6. Binary source: extracted from Termux packages (~900 KB per arch)

Source: [PR #338](https://github.com/yausername/youtubedl-android/pull/338),
[Issue #337](https://github.com/yausername/youtubedl-android/issues/337)

### ytdlp-jsc plugin (in-process alternative)

[`ytdlp-jsc`](https://github.com/ahaoboy/ytdlp-jsc) embeds QuickJS via
Rust/PyO3, solving YouTube JS challenges in-process. Performance is 1.44x
slower than CLI QuickJS but competitive due to eliminated subprocess startup.
**No Android wheels exist.**

Source: [PyPI ytdlp-jsc](https://pypi.org/project/ytdlp-jsc/)

---

## Comparison of approaches

| Approach | APK size | Complexity | W^X safe | yt-dlp compat | Proven on Android |
|----------|----------|------------|----------|---------------|-------------------|
| **gd3qjs recipe** (cross-compile + nativeLibraryDir) | +~1 MB | Low (follows gd3ffmpeg pattern) | Yes | Yes (`--js-runtimes`) | Yes (youtubedl-android) |
| linker64 + downloaded binary | +0 (downloaded) | Medium (runtime download + linker64) | Yes (via hack) | Yes | Yes (N_m3u8DL-RE) |
| quickjs-rs + wasmtime (in-process) | +~15 MB | Medium (dependency management) | Yes (no exec) | No (needs yt-dlp changes) | No |
| quickjs-ng Python C extension (p4a recipe) | +~1 MB | High (custom C extension recipe) | Yes (no exec) | No (needs yt-dlp changes) | No |
| Linux aarch64 static binary (from releases) | +~2 MB | Low (download + linker64) | Needs linker64 | Yes | Partially (#1512) |

---

## Recommendation

### Build a `gd3qjs` p4a recipe (nativeLibraryDir approach)

This is the clear winner:

1. **Proven pattern** -- identical to `gd3ffmpeg` in this project and
   `youtubedl-android`'s approach
2. **No linker64 hack** -- nativeLibraryDir is the system-blessed execution
   path
3. **Tiny size** -- ~1 MB added to APK
4. **Trivial to build** -- QuickJS-NG is pure C11, CMake, cross-compiles in
   ~5 lines with NDK
5. **Direct yt-dlp compatibility** -- configure with
   `--js-runtimes quickjs:<nativeLibraryDir>/libqjs.so`
6. **No yt-dlp changes needed** -- works with yt-dlp's existing subprocess
   mechanism

Implementation:
1. Add NDK cross-compilation step to `android/Dockerfile` (pin to a
   QuickJS-NG release tag)
2. Create `android/recipes/gd3qjs/__init__.py` following the `gd3ffmpeg`
   pattern
3. Add `gd3qjs` to the p4a requirements in the build script
4. At runtime, locate `libqjs.so` in nativeLibraryDir and pass its path
   to yt-dlp via `--js-runtimes`

### Not recommended

- **linker64 approach**: works but is a hack. nativeLibraryDir is cleaner
  for bundled binaries. Reserve linker64 for runtime-downloaded binaries
  only (per ADR-0005's original intent).
- **quickjs-rs + wasmtime**: adds ~15 MB, unproven on Android, and
  requires changes to yt-dlp's JS runtime integration.
- **In-process Python bindings**: requires either monkey-patching yt-dlp or
  maintaining a yt-dlp plugin. Not worth the complexity when the subprocess
  approach works.
