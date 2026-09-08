#!/usr/bin/env bash
set -euo pipefail

# Download pre-built Android arm64 binaries for jniLibs
#
# Binaries:
#   - ffmpeg + ffprobe (Ghost-Downloader-FFmpeg)
#   - N_m3u8DL-RE
#   - QuickJS-NG (qjs)
#
# Usage:
#   ./fetch_android_libs.sh
#
# Output:
#   ../app/src/main/jniLibs/arm64-v8a/lib{ffmpeg,ffprobe,nm3u8dlre,qjs}.so

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JNILIBS_DIR="${SCRIPT_DIR}/../app/src/main/jniLibs/arm64-v8a"

FFMPEG_TAG="n8.1.2-gd1"
NM3U8_TAG="v0.6.0-beta"
NM3U8_ASSET="N_m3u8DL-RE_${NM3U8_TAG}_android-bionic-arm64_20260629.tar.gz"
QJS_TAG="v0.15.1"

mkdir -p "$JNILIBS_DIR"
TMP="$(mktemp -d)"
trap "rm -rf '$TMP'" EXIT

# --- FFmpeg + ffprobe ---

if [ -f "$JNILIBS_DIR/libffmpeg.so" ] && [ -f "$JNILIBS_DIR/libffprobe.so" ]; then
    echo "ffmpeg ($FFMPEG_TAG): already present"
else
    echo "Downloading ffmpeg ${FFMPEG_TAG}..."
    curl -fSL "https://github.com/XiaoYouChR/Ghost-Downloader-FFmpeg/releases/download/${FFMPEG_TAG}/ffmpeg-android-arm64.tar.gz" \
        | tar xz -C "$TMP"
    cp "$TMP/ffmpeg" "$JNILIBS_DIR/libffmpeg.so"
    cp "$TMP/ffprobe" "$JNILIBS_DIR/libffprobe.so"
    chmod +x "$JNILIBS_DIR/libffmpeg.so" "$JNILIBS_DIR/libffprobe.so"
    echo "  -> $(ls -lh "$JNILIBS_DIR/libffmpeg.so" | awk '{print $5}') libffmpeg.so"
    echo "  -> $(ls -lh "$JNILIBS_DIR/libffprobe.so" | awk '{print $5}') libffprobe.so"
fi

# --- N_m3u8DL-RE ---

if [ -f "$JNILIBS_DIR/libnm3u8dlre.so" ]; then
    echo "N_m3u8DL-RE ($NM3U8_TAG): already present"
else
    echo "Downloading N_m3u8DL-RE ${NM3U8_TAG}..."
    curl -fSL "https://github.com/nilaoda/N_m3u8DL-RE/releases/download/${NM3U8_TAG}/${NM3U8_ASSET}" \
        | tar xz -C "$TMP"
    cp "$TMP/N_m3u8DL-RE" "$JNILIBS_DIR/libnm3u8dlre.so"
    chmod +x "$JNILIBS_DIR/libnm3u8dlre.so"
    echo "  -> $(ls -lh "$JNILIBS_DIR/libnm3u8dlre.so" | awk '{print $5}') libnm3u8dlre.so"
fi

# --- QuickJS-NG ---

if [ -f "$JNILIBS_DIR/libqjs.so" ]; then
    echo "qjs ($QJS_TAG): already present"
else
    echo "Downloading QuickJS-NG ${QJS_TAG}..."
    curl -fSL "https://github.com/quickjs-ng/quickjs/releases/download/${QJS_TAG}/qjs-linux-aarch64" \
        -o "$JNILIBS_DIR/libqjs.so"
    chmod +x "$JNILIBS_DIR/libqjs.so"
    echo "  -> $(ls -lh "$JNILIBS_DIR/libqjs.so" | awk '{print $5}') libqjs.so"
fi

echo ""
echo "Done. jniLibs:"
ls -lh "$JNILIBS_DIR"/lib*.so
