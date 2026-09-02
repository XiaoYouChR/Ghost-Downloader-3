# Android native binary execution via linker64, ffmpeg stays pre-bundled

Android 10+ enforces W^X: files outside the APK's `nativeLibraryDir` cannot
be executed. Downloaded binaries (N_m3u8DL-RE) must be invoked through
`/system/bin/linker64 <path>` to bypass SELinux exec restrictions. This has
been validated on-device.

FFmpeg must stay pre-bundled in `nativeLibraryDir` (via the `gd3ffmpeg` p4a
recipe). N_m3u8DL-RE internally exec's ffmpeg as a child process and does not
use our linker64 wrapper — if ffmpeg is outside `nativeLibraryDir`,
N_m3u8DL-RE's internal exec fails silently.

Only N_m3u8DL-RE can be runtime hot-installed (~20 MB APK savings).
Implementation is deferred.

## Considered Options

- **Bundle all binaries in nativeLibraryDir** — rejected as the long-term
  goal: N_m3u8DL-RE is ~20 MB and updates independently of the app. Bundling
  it inflates the APK and requires a full app update for runtime upgrades.
- **Use app_process instead of linker64** — rejected: `app_process` requires
  Java class loading, not suitable for plain native executables.
