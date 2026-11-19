# m3u8 字幕只作为 Side File，不混入成品

m3u8_pack 的字幕一律作为 Side File 下载：每种选中的语言一个独立运行 N_m3u8DL-RE `--sub-only` 的 Step，主 Step 不下载字幕，默认不选任何字幕。N_m3u8DL-RE 把字幕混进 mp4 要用 `mov_text`，混进 mkv 要用 `srt`/`webvtt`，都需要字幕编码器，而 [ADR 0002](./0002-minimal-lgpl-self-built-ffmpeg.md) 的精简 FFmpeg 不带任何编码器；混流失败后只剩无声的视频轨（#1031）。字幕 Step 独立联网，是为了让已完成的 Task 新启用字幕时能 Revive，而不依赖完成后已删除的 Part Path。

## Considered Options

- **给自建 FFmpeg 加字幕编解码器**：越过 ADR 0002 "不转码"的边界，需要跨仓库发版、用户重下 FFmpeg；X 自动字幕里的 `<X-word-ms>` 私有标签照样会进成品。
- **主 Step 结束后顺手把 .srt 移出 Part Path**：没有 Placeholder，违反 [ADR 0014](./0014-disk-is-the-truth-for-name-conflict.md)，也无法 Revive。
