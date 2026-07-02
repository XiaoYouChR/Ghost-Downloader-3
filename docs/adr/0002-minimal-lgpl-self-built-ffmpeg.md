Status: accepted — implemented at https://github.com/XiaoYouChR/Ghost-Downloader-FFmpeg

# Ship a minimal, LGPL, self-built FFmpeg instead of a full prebuilt

Ghost Downloader bundles FFmpeg for three jobs only: stream-copy remux
(`bili_pack`, `ffmpeg_pack`), muxing + AES-128 decryption driven by N_m3u8DL-RE
(`m3u8_pack`), and yt-dlp post-processing (merge bestvideo+bestaudio, embed
metadata/chapters/thumbnail). **No call site ever transcodes audio or video.**
The only encoders touched are `mjpeg`/`png`, when yt-dlp converts a webp
thumbnail for an mp4 container.

The current desktop install pulls BtbN's GPL static build (~80 MB zip, Windows
only) and even scores `-gpl` higher; Android ships hzw1199's comprehensive LGPL
build (~30 MB of `ffmpeg`+`ffprobe`). Both carry a full encoder/filter suite
that this app never invokes.

## Decision

Build our own **minimal, LGPL** FFmpeg (`--disable-everything` + an exact
whitelist of demuxers/muxers/bitstream-filters/protocols, plus `mjpeg`/`png`
encoders for thumbnails, `--enable-small`), targeting ~4–6 MB per platform.

- **Where:** a dedicated build repo with a GitHub Actions matrix — fork BtbN's
  Docker cross-compile for win64/arm64 + linux x64/arm64, add a native macOS
  runner (x64/arm64) and an Android NDK lane (arm64, minSdk 28, no MediaCodec).
  One configure spec feeds all four platforms.
- **Versioning:** pin FFmpeg 8.1.x stable (matches today's Android 8.1.1), tag
  builds `n8.1.1-gd1…`, app fetches our own `/releases/latest` so FFmpeg
  security fixes ship without an app update.
- **Correctness:** each build job runs real-asset smoke tests (bv+ba→mp4 remux,
  HLS AES-128 decrypt+mux, fmp4/m4s, EAC3, webp→mp4 thumbnail, ffprobe
  duration). Any failure blocks the release — a missing demuxer fails CI, not a
  user download.
- **Delivery:** reuse `github_pack` for CN acceleration + a fallback to direct
  GitHub, and verify a published SHA256 after download.

## Considered Options

- **Keep BtbN GPL static (status quo).** Rejected: ~80 MB for a remux-only use
  case, ships GPLv3 binaries with the app (a licensing liability), Windows only.
- **Switch to BtbN LGPL static.** Rejected as the end goal: removes the GPL
  liability and shrinks somewhat, but still bundles a full encoder/filter suite
  we never call. Kept in mind only as a possible emergency fallback source.
- **gyan.dev essentials (~32 MB 7z).** Rejected: still GPLv3, still bundles
  x264/x265 etc.; not meaningfully smaller for our needs; no LGPL/minimal
  variant.
- **Self-built minimal (chosen).** Largest shrink (~80 MB → ~4–6 MB) and the
  only option that ships exactly what we use. Cost: we own a CI build pipeline
  and FFmpeg security bumps — accepted, and bounded by the smoke-test gate.

## Implementation seams

The mirror is **not** a new mechanism — installs route through the one universal
router, `featureService.parse`, where `GitHubParser` (priority 90) already
rewrites GitHub URLs to a mirror by delegating back through `parse`. The
`MergeParser` precedent is the template: it never touches HTTP or mirrors; it
routes its sub-resources through `featureService.parse(options.video)` and lets
the router decide. An install's *download* is the same — a sub-resource to parse.

- **`BinaryInstallOptions` + `InstallParser` (disk_pack, priority 55).** A
  runtime emits `BinaryInstallOptions(url, outputFolder, name, executableNames,
  sha256Url)` and calls `featureService.parse`. `InstallParser` delegates the
  download (and the `.sha256`) back through `featureService.parse(TaskOptions(...))`
  so `GitHubParser` mirrors them, then wraps with checksum/extract/install (archive)
  or chmod (single binary). Runtimes and `disk_pack` never import `github_pack`.
- **Archive vs single-binary unified** under `InstallParser`, branching on asset
  extension (`.zip`/`.tar.gz` → extract; else chmod).
- **`ChecksumStep` (disk_pack)** verifies the downloaded asset against the
  downloaded `.sha256` (both are local files — the step is mirror-agnostic).
- **`removeQuarantine(path)`** in `InstallStep` and `BinaryInstallStep` after
  chmod, darwin-only, so a downloaded `ffmpeg` is not killed by Gatekeeper.
