# Android Build Notes

Build and packaging knowledge for the PySide6 + python-for-android (p4a)
Android target. Minimum supported version: Android 10 (API 29).

## Docker CI

The build runs in a custom Docker image with p4a, Android SDK/NDK, and Rust
toolchain pre-installed. The Dockerfile lives in the CI workflow.

### p4a template patches

p4a copies template files (AndroidManifest, themes, resources) from
`/opt/p4a/pythonforandroid/bootstraps/qt/build/` into the dist. **Patches to
these templates are applied in the Docker image layer**, not in the
buildozer cache volume — the cache gets overwritten on every dist assembly.

Template patches are `sed` commands at the end of the Dockerfile, after the
p4a install step. Three critical PythonActivity patches:

**Back-key → moveTaskToBack**: without this patch, pressing back calls
`onDestroy` + `killProcess`, killing downloads. The patch overrides
`onKeyDown` to call `moveTaskToBack(false)` instead.

**onActivityResult → super()**: without this patch, `QFileDialog` on Android
deadlocks — `PythonActivity` never propagates the result to Qt.

**onNewIntent → setIntent(intent)**: without this patch, re-entry via share
intent returns the stale intent from the first launch (`sharedText()` sees
old data).

### Recipes

Custom p4a recipes live in `android/recipes/`:

- `jh2` — HTTP/2 with Rust extension (requires Rust toolchain in the image)
- `wreq` — TLS fingerprint HTTP client (Rust + btls-sys)
- `gd3ffmpeg` — pre-built FFmpeg binaries into `nativeLibraryDir`

## APK size

The base APK was reduced from ~159 MB to ~62 MB via:

- Pruning unused Python stdlib modules (`android/patches/gd3_prune.py`)
- Pre-built minimal FFmpeg instead of full build (~30 MB → ~6 MB)
- N_m3u8DL-RE excluded from APK (runtime hot-install via linker64, see
  ADR 0005)

## Signing

Release keystore: `~/.gd3-android/release.jks`
- Alias: `ghostdownloader`
- First public release uses this keystore — Android binds the signing
  key permanently to the package name (see ADR 0006)

CI secrets (GitHub Actions):
- `ANDROID_KEYSTORE_BASE64` — base64-encoded `.jks`
- `ANDROID_KEYSTORE_PASSWORD` — keystore + key password (same)
- `ANDROID_KEY_ALIAS` — `ghostdownloader`

## Runtime patches (`patches.py`)

`app/view/mobile/patches.py` applies monkey-patches for PySide6-on-Android
quirks. All patches are called from `app/view/mobile/__init__.py` during
`setupAndroid()`.

| Patch | What it fixes |
|---|---|
| `patchMenus` | RoundMenu reparented as child widget — second top-level window crashes EGL (ADR 0004) |
| `patchIconRendering` | QSvgPlugin returns blank pixmaps → SvgIconEngine renders via QSvgRenderer |
| `patchFileDialogs` | QFileDialog `content://` URIs → real filesystem paths via ContentResolver |
| `patchDialogWidth` | MessageBoxBase limited to screen width on narrow devices |
| `patchOptionCardLayout` | Horizontal setting/option cards reflowed to vertical |
| `patchGroupTouch` | CollapsibleSettingCardGroup header tap toggles collapse (touch-friendly) |

## Storage permission

Android 11+ (API 30): `MANAGE_EXTERNAL_STORAGE` — broad file access, required
for downloading to arbitrary folders. Android 10 and below:
`WRITE_EXTERNAL_STORAGE`. `PermissionBanner` in `MobileMainWindow` blocks
task creation until storage is granted.

## StrictMode file URI

Android 7+ (API 24) blocks `file://` URIs in intents by default.
`_relaxFileUriPolicy()` in `app/platform/android.py` disables StrictMode's
`FileUriExposedException` check so `Uri.fromFile` intents (open file, reveal
folder) work.

## Device debugging pitfalls

### Screen-off pauses the Qt event loop

When the screen turns off, Android pauses the activity. The Qt event loop
stops processing — downloads freeze. The `KeepAlive` foreground service +
`PARTIAL_WAKE_LOCK` keeps the CPU running, but the Qt event loop only
resumes when the screen is on or the activity is in the foreground.

### Insets double-inset

Android system bars insets can be applied twice if both the activity theme
and Qt handle them. Fix: let the activity theme handle status bar color,
do not apply insets in Qt layout code.

### Desktop preview via grab()

For fast UI iteration without deploying to a real device, use
`widget.grab().save("preview.png")` to render the widget off-screen on
desktop. This works because `MobileMainWindow` is a plain `QWidget` with
no Android-specific rendering.
