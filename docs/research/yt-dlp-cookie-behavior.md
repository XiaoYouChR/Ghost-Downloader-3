# yt-dlp Cookie & Authentication Behavior for YouTube

Research date: 2026-07-04

---

## 1. Error Behavior When Authentication Is Missing

### Age-Restricted Videos (No Cookies)

yt-dlp produces a **fatal `ExtractorError`** and exits. The error originates from `raise_no_formats()` in `_real_extract()` at approximately line 4061 of `yt_dlp/extractor/youtube/_video.py`.

Exact error message:
```
ERROR: [youtube] <video_id>: Sign in to confirm your age.
  This video may be inappropriate for some users.
```

An informational message is also emitted:
```
[youtube] <video_id>: This video is age-restricted; some formats may be missing
  without authentication. Use --cookies-from-browser or --cookies for the
  authentication. See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp
  for how to manually pass cookies
```

The YouTube player API returns `playability_status: LOGIN_REQUIRED` for all attempted clients (android_vr, web_safari, etc.), which triggers the error.

**`--dump-json` fails** in this scenario. The error occurs during extraction before format data is assembled, so no JSON is output. The process exits with a non-zero code.

Sources:
- [Issue #11296: Age-restricted videos now always require sign-in](https://github.com/yt-dlp/yt-dlp/issues/11296)
- [Issue #16351: Age restriction bypass without account](https://github.com/yt-dlp/yt-dlp/issues/16351)
- [Issue #16553: yt-dlp routinely fails to download youtube videos](https://github.com/yt-dlp/yt-dlp/issues/16553)

### Members-Only Videos

yt-dlp produces a **fatal error** with YouTube's own restriction message:
```
ERROR: Join this channel to get access to members-only content like this video,
  and other exclusive perks.
```

The extraction fails completely for the individual video. When processing a playlist, yt-dlp skips the failed video and continues to the next item.

Source: [Issue #9368: Membership Restricted Video Issue](https://github.com/yt-dlp/yt-dlp/issues/9368)

### Bot Detection ("Sign in to confirm you're not a bot")

This is **not an authentication issue per se** -- it is YouTube's rate-limiting/bot-detection. The error is:
```
ERROR: [youtube] <video_id>: Sign in to confirm you're not a bot.
  Use --cookies-from-browser or --cookies for the authentication.
```

This affects even public, non-restricted videos. All player clients return `playability_status: LOGIN_REQUIRED`. yt-dlp exits with an error. Providing valid cookies resolves it (the cookies prove the request comes from a real browser session).

Sources:
- [Issue #12045: yt-dlp continuing to prompt for cookies with --cookies used](https://github.com/yt-dlp/yt-dlp/issues/12045)
- [Issue #15865: All public YouTube videos require login](https://github.com/yt-dlp/yt-dlp/issues/15865)

### Key Point: No "Requested format is not available" for Auth Issues

When authentication is completely missing for restricted content, yt-dlp does **not** report "requested format is not available." It reports the specific restriction reason from YouTube's `playability_status` response. The "requested format is not available" error occurs in different scenarios (wrong format string, SABR streaming issues, bad working directory).

Source: [Issue #16006: Bad working directory causes nonsensical "Requested format is not available" error](https://github.com/yt-dlp/yt-dlp/issues/16006)

---

## 2. `--cookies-from-browser` Failure Behavior

### Cookie loading failures are FATAL

Since commit [e59c82a](https://github.com/yt-dlp/yt-dlp/commit/e59c82a74cda5139eb3928c75b0bd45484dbe7f0) (October 2024), cookie load failures are handled via a dedicated `CookieLoadError` exception. The behavior is:

1. Any exception during cookie extraction is caught and re-raised as `CookieLoadError('failed to load cookies')`
2. `YoutubeDL.py` catches `CookieLoadError`, logs the full traceback, and re-raises
3. The CLI handler in `__init__.py` catches `CookieLoadError` alongside `DownloadError` and calls `_exit(1)`

```python
# cookies.py
except Exception:
    raise CookieLoadError('failed to load cookies')

# __init__.py
except (CookieLoadError, DownloadError):
    _exit(1)
```

**yt-dlp does NOT fall back to no-cookie mode.** It exits with code 1.

Source: [Commit e59c82a: Fix cookie load error handling](https://github.com/yt-dlp/yt-dlp/commit/e59c82a74cda5139eb3928c75b0bd45484dbe7f0)

### Specific Failure Scenarios

| Scenario | Behavior |
|----------|----------|
| Browser not installed / profile not found | `FileNotFoundError` -> `CookieLoadError` -> exit(1) |
| Cookie DB locked (Windows, Chrome open) | `PermissionError` -> `DownloadError` -> exit(1) with message: "Could not copy Chrome cookie database" |
| Cookie decryption failure | Warning logged, but continues with empty/partial cookies (does not exit) |
| Missing sqlite3 module | Warning logged, returns empty jar (continues without cookies) |
| Invalid cookie file format (--cookies) | Error: "'cookies.txt' does not look like a Netscape format cookies file" |

The Windows Permission denied case has special handling:
```python
if os.name == 'nt' and error.errno == 13:
    message = 'Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271 for more info'
    logger.error(message)
    raise DownloadError(message)
```

Sources:
- [Issue #7271: Permission denied errors when Chrome is open](https://github.com/yt-dlp/yt-dlp/issues/7271)
- [cookies.py source](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/cookies.py)
- [Issue #10927: failed to decrypt with DPAPI](https://github.com/yt-dlp/yt-dlp/issues/10927)

### Important Nuance: Decryption Failures vs. Load Failures

Cookie *decryption* failures (e.g., wrong DPAPI key, MAC check failed) emit warnings but may still return a partially populated cookie jar. This means yt-dlp can continue with cookies that are present but not properly decrypted -- effectively running with incomplete/invalid cookies rather than exiting. The distinction is:
- **Cannot open/find the database at all** -> Fatal exit
- **Can open the database but some cookies fail to decrypt** -> Warning, continues with whatever cookies it could read

Source: [Issue #10927: failed to decrypt with DPAPI / NoneType error](https://github.com/yt-dlp/yt-dlp/issues/10927)

---

## 3. Detecting Whether Cookies Are Active/Effective

### `--dump-json` Output Fields

The JSON output from `--dump-json` includes these relevant fields:

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `age_limit` | int | `0` or `18` | Age restriction for the video |
| `availability` | string | `"public"`, `"unlisted"`, `"needs_auth"`, `"premium_only"`, `"subscriber_only"`, `"private"` | Access restriction level |
| `playable_in_embed` | bool | | Whether embeddable on other sites |

Source: [yt-dlp README, OUTPUT TEMPLATE section](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)

### No Explicit "Authenticated" Field

There is **no field** in the `--dump-json` output that indicates whether the current request is authenticated. There is no `is_premium`, `is_authenticated`, or `user_is_subscriber` field in the output JSON.

### How yt-dlp Detects Authentication Internally

Internally, the YouTube extractor uses the constant `STREAMING_DATA_IS_PREMIUM_SUBSCRIBER` and logs "Detected YouTube Premium subscription" when Premium cookies are present. However, **this information is only in debug/verbose logs, not in the JSON output**.

Source: [YouTube extractor source, _video.py](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_video.py)

### The `availability` Field Has Gaps

The `availability` field only reliably returns three values for YouTube:
- `"public"` -- publicly accessible
- `"unlisted"` -- unlisted videos
- `"needs_auth"` -- age-restricted content

For content that causes extraction errors (private, members-only, copyright-blocked), the field is **not populated** because the extraction fails before the field can be set. The error message is the only indicator.

Source: [Issue #9845: Availability tag doesn't work as intended](https://github.com/yt-dlp/yt-dlp/issues/9845)

### Practical Detection Strategy

The only reliable way to detect effective authentication from yt-dlp output is:
1. **Compare format lists**: Authenticated requests may yield additional formats (especially Premium itags)
2. **Check verbose logs**: Look for "Detected YouTube Premium subscription" in `-v` output
3. **Check which clients were used**: Verbose output shows client selection (authenticated sessions use `tv_downgraded` + `web_safari`/`web_creator` instead of `android_sdkless` + `web_safari`)

---

## 4. What YouTube Restricts for Unauthenticated Requests

### Client Selection Differs by Auth State

The YouTube extractor selects different API clients based on authentication:

| State | Default Clients |
|-------|----------------|
| No cookies | `android_sdkless`, `web`, `web_safari` |
| No JS runtime | `android_sdkless` only |
| Free account (cookies) | `tv_downgraded`, `web`, `web_safari` |
| Premium account (cookies) | `tv_downgraded`, `web_creator`, `web` |

`web_creator` **only works with authentication** -- it cannot be used without cookies.

Source: [Commit 23b8465: Adjust default clients](https://github.com/yt-dlp/yt-dlp/commit/23b846506378a6a9c9a0958382d37f943f7cfa51)

### Content Completely Blocked Without Authentication

| Content Type | Behavior Without Auth |
|-------------|----------------------|
| Age-restricted videos | Fatal error, no download possible |
| Members-only videos | Fatal error, no download possible |
| Private videos | Fatal error, no download possible |
| Bot-detected sessions | Fatal error until cookies provided |

Age-restricted videos have **no bypass mechanism** without authentication. The old `yt-dlp-YTAgeGateBypass` project is defunct. The `web_embedded` client sometimes works for embeddable age-restricted videos, but YouTube has been closing this loophole.

Sources:
- [Issue #16351: Age restriction bypass without account](https://github.com/yt-dlp/yt-dlp/issues/16351)
- [Issue #11296: Age-restricted videos now always require sign-in](https://github.com/yt-dlp/yt-dlp/issues/11296)

### Format Availability Differences

**Standard public videos**: Format lists are generally the same for authenticated and unauthenticated requests. Standard resolutions (360p through 4K) are available without authentication for non-restricted content.

**YouTube Premium exclusive formats**: Premium accounts get additional DASH format itags that are not available to free accounts:
- itag 356 (1080p VP9, Premium-exclusive)
- itag 315 (2160p60 VP9, Premium-exclusive)
- itag 401 (2160p AV1, Premium-exclusive)

Standard equivalents (itag 137 for 1080p H.264, itag 248 for 1080p VP9) remain available to free accounts. The Premium itags offer higher bitrate or different codec variants at the same resolution.

Source: [Issue #14669: Premium 1080p (itag 356) formats missing](https://github.com/yt-dlp/yt-dlp/issues/14669)

### Rate Limiting Differences

| Session Type | Approximate Rate Limit |
|-------------|----------------------|
| Guest (no cookies) | ~300 videos/hour |
| Authenticated account | ~2000 videos/hour |

Source: [yt-dlp Wiki: Extractors](https://github.com/yt-dlp/yt-dlp/wiki/extractors)

### Region-Locked Content

yt-dlp does not have special handling for region-locked content. If a video is unavailable in the requesting IP's region, YouTube returns an `UNPLAYABLE` playability status, and yt-dlp reports the error from YouTube's response. Using `--geo-bypass` or a proxy is the recommended workaround, but this is independent of cookie/authentication state.

---

## Summary Table

| Question | Answer |
|----------|--------|
| Auth missing + age-restricted video | Fatal `ExtractorError`: "Sign in to confirm your age" |
| Auth missing + members-only video | Fatal error: "Join this channel to get access..." |
| Auth missing + public video (bot-detected) | Fatal error: "Sign in to confirm you're not a bot" |
| `--dump-json` with restricted content | Fails (error before JSON assembly) |
| `--cookies-from-browser` + browser not found | Fatal `CookieLoadError`, exit(1) |
| `--cookies-from-browser` + locked DB (Windows) | Fatal `DownloadError`, exit(1) |
| `--cookies-from-browser` + decryption failure | Warning only, continues with partial cookies |
| JSON field for auth state | None (no `is_authenticated` field) |
| JSON `availability` for restricted | `"needs_auth"` for age-restricted; empty for others that fail |
| Format differences: free vs premium | Premium gets exclusive itags (356, 315, 401); standard codecs available to all |
| Rate limit: guest vs authenticated | ~300 vs ~2000 videos/hour |
