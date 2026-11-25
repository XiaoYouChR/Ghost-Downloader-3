# Android 增量更新用 HDiffPatch 直接差分 APK，不用 ApkDiffPatch

Android 补丁更新复用桌面端的 HDiffPatch（`hdiffz -f -c-lzma2` 配合官方 Android SDK 的 JNI `libhpatchz.so`），直接对 Gradle 签好名的发布 APK 做文件级差分，不采用 [ApkDiffPatch](https://github.com/sisong/ApkDiffPatch)。

因为 `android/app/build.gradle.kts` 开启了 `jniLibs.useLegacyPackaging = true`，所有 `.so`（约 20.3 MiB）以 `DEFLATE` 存储且常规发版极少变动，而常规发版变动的 `classes.dex`、`resources.arsc`、`app.imy`、`requirements-common.imy` 全为 `STORE`（未压缩）。在真实发布包 `v4.5.8 -> v4.5.11`（整包 45.08 MiB）上实测，HDiffPatch 产出的补丁为 2.03 MiB（占整包 4.5%），与 `ApkDiffPatch`（2.03 MiB）几乎一致，且端侧 `libhpatchz.so` 仅 98.5 KB（已 16 KB 对齐、仅依赖 `libc.so`）、合成无需重压缩、无需改动 Gradle 的 APK v2/v3 签名链路。

## Considered Options

- **ApkDiffPatch v1.8.1（`ApkNormalized` + `apksigner` + `ZipDiff/ZipPatch`）**：仅在某次发版恰好升级较大 `.so`（如 `libkelpie.so`、`libffmpeg.so`）时可多省 1~2 MiB；但必须改造发版流程在 `ApkNormalized` 后重签，且 v1.8.1 不兼容 Android SDK `apksigner` v35/v36（Issue #96，PR #109 尚未合并），CI 需要锁死 `build-tools` v34，端侧合成还要重跑 zlib 压缩、耗时更高。
- **sfpatcher**：无需重签且支持嵌套压缩包，但为闭源商业授权。

## Consequences

- 某次发版若升级了较大的 `DEFLATE` `.so`，该版本补丁会多出对应 `.so` 压缩后的体积（约 1~3 MiB），仍远小于整包。
- `versions.json` 的 `app.patches` 在桌面端与 Android 保持相同的 4 字段结构，不新增 `baseSha256`；Android 合成后以 `app.full["Android-arm64"].sha256` 校验产物，任意失败自动回退全量下载。
