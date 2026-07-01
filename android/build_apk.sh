#!/usr/bin/env bash

set -euo pipefail

WHEEL_DIR=/opt/qt-android-wheels
ANDROID_DIR=/work
REPO=/repo
STAGE=/home/builder/stage

mkdir -p "$STAGE"
rm -rf "$STAGE/app" "$STAGE/features"
cp -a "$REPO/app" "$STAGE/app"
cp -a "$REPO/features" "$STAGE/features"
cp -a "$ANDROID_DIR/main.py" "$STAGE/main.py"
rm -rf "$STAGE/features/bittorrent_pack"
rm -rf "$STAGE/features/ed2k_pack"
rm -rf "$STAGE/features/jack_yao"
rm -rf "$STAGE/features/yt_dlp_pack"
find "$STAGE/app" "$STAGE/features" -name "__pycache__" -type d -prune -exec rm -rf {} +

cd "$STAGE"

rm -f "$STAGE/pysidedeploy.spec" "$STAGE/buildozer.spec"

find "$STAGE" -name "*.apk" -delete
BUILD_MARKER="$STAGE/.build_marker"
touch "$BUILD_MARKER"

export GD3_EXTRA_REQ="${GD3_EXTRA_REQ:-,pyjnius,wreq,charset-normalizer,idna,PySide6-Fluent-Widgets,PySideSix-Frameless-Window,darkdetect,loguru,qrcode,pypng,m3u8,mpegdash,aioftp,gd3ffmpeg}"
export GD3_EXTRA_PERM="${GD3_EXTRA_PERM:-,MANAGE_EXTERNAL_STORAGE,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,WAKE_LOCK}"

export GD3_ICON="${GD3_ICON:-$REPO/app/assets/logo.png}"

export GD3_ICON_FG="${GD3_ICON_FG:-$ANDROID_DIR/res/icon_foreground.png}"
export GD3_ICON_BG="${GD3_ICON_BG:-$ANDROID_DIR/res/icon_background.png}"

export GD3_RES="${GD3_RES:-$ANDROID_DIR/res/values-night/colors.xml:values-night/colors.xml,$ANDROID_DIR/res/splash_logo.png:drawable-nodpi/gd3_splash_logo.png,$ANDROID_DIR/res/drawable/gd3_splash.xml:drawable/gd3_splash.xml}"

export GD3_APP_TITLE="${GD3_APP_TITLE:-Ghost Downloader}"
export GD3_PKG_NAME="${GD3_PKG_NAME:-ghostdownloader}"
export GD3_PKG_DOMAIN="${GD3_PKG_DOMAIN:-io.github.xiaoyouchr}"

export GD3_VERSION="${GD3_VERSION:-$(grep -oP '^VERSION = "\K[^"]+' "$REPO/app/config/constants.py")}"

export GD3_QT_MODULES="${GD3_QT_MODULES:-Core,Gui,Widgets,Network,Svg,SvgWidgets,WebSockets,Xml}"
echo "[build] STAGE=$STAGE"
echo "[build] applicationId=$GD3_PKG_DOMAIN.$GD3_PKG_NAME  label=$GD3_APP_TITLE"
echo "[build] adaptive icon fg=$GD3_ICON_FG bg=$GD3_ICON_BG"
echo "[build] GD3_EXTRA_REQ=$GD3_EXTRA_REQ  GD3_EXTRA_PERM=$GD3_EXTRA_PERM"
echo "[build] GD3_QT_MODULES=$GD3_QT_MODULES"

PYSIDE_WHL=$(ls "$WHEEL_DIR"/PySide6-*android_aarch64.whl)
SHIBOKEN_WHL=$(ls "$WHEEL_DIR"/shiboken6-*android_aarch64.whl)
echo "[build] PySide6  wheel: $PYSIDE_WHL"
echo "[build] shiboken wheel: $SHIBOKEN_WHL"

pyside6-android-deploy -f -v \
    --name GhostDownloaderProbe \
    --wheel-pyside "$PYSIDE_WHL" \
    --wheel-shiboken "$SHIBOKEN_WHL"

mkdir -p "$ANDROID_DIR/dist"

FRESH_APK=$(find "$STAGE" -name "*.apk" -newer "$BUILD_MARKER" -printf "%T@ %p\n" 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
rm -f "$BUILD_MARKER"
if [ -z "$FRESH_APK" ]; then
    echo "[build] 错误：未找到本次新生成的 APK！" >&2
    exit 1
fi
cp -v "$FRESH_APK" "$ANDROID_DIR/dist/"

if [ -n "${GD3_KEYSTORE:-}" ]; then
    BUILD_TOOLS=$(ls -d "$HOME"/.buildozer/android/platform/android-sdk/build-tools/*/ 2>/dev/null | sort -V | tail -1)
    if [ -z "$BUILD_TOOLS" ]; then echo "[build] 错误：找不到 build-tools(apksigner/zipalign)" >&2; exit 1; fi
    DEBUG_APK="$ANDROID_DIR/dist/$(basename "$FRESH_APK")"
    RELEASE_APK="${DEBUG_APK%-debug.apk}-release.apk"
    "${BUILD_TOOLS}zipalign" -f -p 4 "$DEBUG_APK" "$RELEASE_APK"
    "${BUILD_TOOLS}apksigner" sign --ks "$GD3_KEYSTORE" \
        --ks-pass "pass:$GD3_KEYSTORE_PASS" \
        --ks-key-alias "$GD3_KEY_ALIAS" \
        --key-pass "pass:${GD3_KEY_PASS:-$GD3_KEYSTORE_PASS}" \
        "$RELEASE_APK"
    "${BUILD_TOOLS}apksigner" verify --print-certs "$RELEASE_APK" >/dev/null && echo "[build] 已签名 release: $RELEASE_APK"
    rm -f "$DEBUG_APK"
fi

echo "[build] 产物（本次新构建）："
ls -la "$ANDROID_DIR/dist"
