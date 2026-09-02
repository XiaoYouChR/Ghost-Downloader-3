Status: accepted

# Use yt-dlp as a library (extract-only) with QuickJS-NG

yt_dlp_pack currently shells out to a frozen yt-dlp binary (~30 MB) plus a deno
JS runtime (~100 MB). Users must download ~130 MB of external tooling before
YouTube works. The pack is a thin subprocess wrapper (~1,049 lines) that builds
CLI args, spawns `yt-dlp --dump-json` / `yt-dlp <url>`, and parses stdout
progress — it never touches YouTube's API directly.

## Decision

Switch yt_dlp_pack from subprocess mode to **library mode, extract-only**:

- **Install:** download the `yt_dlp` wheel (~3–5 MB) and a QuickJS-NG `qjs`
  binary (~2 MB) at runtime into the pack's vendor directory. One "一键安装"
  button, one Task with three steps (download whl, download qjs, extract/chmod).
  Total: ~7 MB vs ~130 MB.
- **Isolation:** all yt-dlp imports are lazy (`importlib.import_module`), so
  Nuitka's AST scanner in `deploy.py` never sees them. The main binary size is
  unchanged. `deploy.py` requires zero modifications.
- **Extraction:** call `yt_dlp.YoutubeDL.extract_info(url, download=False)` with
  `allowed_extractors=['youtube']` inside `asyncio.to_thread()`. yt-dlp solves
  signature cipher + n-challenge via QuickJS-NG and returns fully decrypted,
  ready-to-download stream URLs.
- **HTTP (extraction phase):** yt-dlp's built-in urllib backend handles extraction
  HTTP (InnerTube API calls, player JS download). These are API endpoints and CDN
  resources that do not require browser TLS fingerprinting. No custom
  `RequestHandler` is needed — urllib is synchronous, thread-safe, and works
  naturally inside `asyncio.to_thread()`.
- **Download:** hand the solved URLs to Ghost-Downloader's own
  `FFmpegResourceStep` (extends `HttpTaskStep`) + wreq. Global rate limiting,
  range-request resume, and browser fingerprint emulation are controlled at this
  layer. yt-dlp's `downloader/` module is never invoked.
- **JS runtime:** QuickJS-NG replaces deno. yt-dlp natively supports it
  (quickjs-ng >= 0.12.0). Pre-built binaries are published by the quickjs-ng
  project for all target platforms (~2 MB each).
- **Updates:** downloading a new `.whl` from PyPI is the same UX pattern as the
  current yt-dlp binary update. yt-dlp's community maintains YouTube extractor
  compatibility (~1–2 critical fixes/month); this pack consumes those fixes by
  fetching the latest wheel.

## Task structure: fixed 4-step with idempotent extraction

A `YouTubeTask` always has exactly four steps, built at parse time:

```
Step 1: YouTubeExtractStep  — extract_info → fill URLs on Step 2 & 3
Step 2: FFmpegResourceStep  — download video track (HttpTaskStep + wreq)
Step 3: FFmpegResourceStep  — download audio track (HttpTaskStep + wreq)
Step 4: FFmpegStep          — stream-copy merge
```

`YouTubeExtractStep` is **idempotent**: `pendingSteps()` always yields it
(regardless of COMPLETED status), and it checks URL freshness before deciding
whether to re-extract. This solves URL expiration on resume:

- **Resume within 6h:** extract step detects fresh URLs → instant skip → download
  resumes from `.ghd` progress. Zero overhead.
- **Resume after 6h:** extract step detects expired URLs → re-extracts (~5–10s) →
  fills fresh URLs on sibling steps → download resumes from `.ghd` (byte ranges
  are content-stable across URL refreshes for the same format).
- **Redownload:** `reset()` sets all steps to WAITING → extract runs from scratch
  → full download. Standard lifecycle, no overrides needed.

Steps are never dynamically added or removed during `run()`. The extract step
writes to existing sibling steps' `url` and `fileSize` fields — it does not
mutate the task's step list.

For pre-merged formats (no separate audio track): the extract step leaves the
audio step's URL empty; the audio step detects this and self-completes; the merge
step detects a single input and renames rather than merging.

Playlists produce N independent `YouTubeTask` instances, each with its own 4-step
lifecycle. No multi-video-in-one-task pattern.

## Considered options

- **Rewrite YouTube extraction from scratch.** Rejected: YouTube's anti-bot
  system requires executing dynamically served JavaScript (n-challenge, signature
  cipher). A JS runtime is an absolute hard dependency — it cannot be removed,
  only repackaged. The YouTube extractor is ~12K lines backed by ~18K lines of
  shared infrastructure, updated ~1–2 times/month for breaking changes. A solo
  maintainer cannot keep up.
- **Fork/strip yt-dlp to YouTube-only, vendor into the pack.** Rejected: the
  initial strip is ~37K lines and straightforward, but upstream changes touch
  youtube/, utils/, common.py, networking/ (~290 commits/18 months). Evaluating
  ~16 commits/month with 1–2 urgent fixes is the same maintenance class as a
  full rewrite.
- **`pip install yt-dlp` as a full package.** Rejected: the app is Nuitka
  standalone, users have no pip. Downloading the wheel and extracting it achieves
  the same result without a package manager.
- **Keep subprocess to yt-dlp binary (status quo).** Rejected: 30 MB binary +
  100 MB deno, no global rate limit control, download logic locked inside
  yt-dlp's process.
- **Inject a WreqRequestHandler into yt-dlp's networking.** Rejected: wreq is
  purely async; yt-dlp's `RequestHandler._send()` is synchronous, and
  `extract_info` runs in `asyncio.to_thread()`. Bridging async→sync adds
  complexity with no benefit — extraction HTTP (InnerTube API, CDN) does not
  need browser TLS fingerprinting. urllib handles it correctly.
- **Dynamic step addition (extract step appends download steps at run time).**
  Rejected: step reaching up to mutate task structure is a seam violation.
  Causes duplicate steps on `redownload` (reset + re-add), requires `reset()`
  override to clean up, and makes progress calculation unstable
  (`len(steps)` changes mid-run). Fixed structure with field-filling is simpler
  and lifecycle-safe.

## Implementation seams

- **`YouTubeRuntime`** replaces both `YtDlpRuntime` and `JsRuntime`. Single
  `installTask()` returns a multi-step Task (download whl + download qjs +
  extract/chmod). `path()` checks both vendor/yt_dlp and qjs exist.
- **`YouTubeExtractStep`** lazily imports yt-dlp (`importlib.import_module`),
  runs `extract_info` in `asyncio.to_thread`, selects best video + audio
  formats, writes URLs and sizes to sibling `FFmpegResourceStep` fields.
  Idempotent: checks URL `expire` param before deciding to re-extract.
- **`YouTubeTask.pendingSteps()`** always yields the extract step (even if
  COMPLETED) so URL freshness is checked on every run.
- **`pack.py`** uses library-mode `extract_info(download=False)` instead of
  subprocess. `YouTubeParser.parse()` builds the fixed 4-step task; extraction
  is deferred to run time.
- **`wreq_handler.py`** does not exist. Extraction uses urllib; download uses
  the existing `HttpTaskStep` + wreq infrastructure.
