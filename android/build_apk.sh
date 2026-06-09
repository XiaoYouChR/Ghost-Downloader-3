#!/usr/bin/env bash
# 在容器内执行：用 pyside6-android-deploy 把真 app 打成 aarch64 APK。
# NDK/SDK 由 deploy 工具自动下载到 ~/.pyside6_android_deploy（通过挂载卷缓存）。
set -euo pipefail

WHEEL_DIR=/opt/qt-android-wheels
ANDROID_DIR=/work             # android/ 构建基础设施（脚本/patches/spec 模板/dist 输出）
REPO=/repo                    # 仓库根（只读挂载）：真 app 源 app/ + features/
STAGE=/home/builder/stage     # 干净的打包工程目录（持久卷，保留 .buildozer 增量）

# 组装打包工程: buildozer 递归打包 cwd 下匹配扩展名的文件, 故须干净的 STAGE(混入的构建脚本会被当 app 打进 APK)。
mkdir -p "$STAGE"
rm -rf "$STAGE/app" "$STAGE/features"
cp -a "$REPO/app" "$STAGE/app"
cp -a "$REPO/features" "$STAGE/features"
cp -a "$ANDROID_DIR/main.py" "$STAGE/main.py"
rm -rf "$STAGE/features/bittorrent_pack"  # libtorrent 无 Android wheel
rm -rf "$STAGE/features/jack_yao"  # 移动端不做资源下载
find "$STAGE/app" "$STAGE/features" -name "__pycache__" -type d -prune -exec rm -rf {} +  # 避免 stale .pyc

cd "$STAGE"

# 删旧 spec 让 deploy 每次 fresh 生成(spec 存在会跳过解析致 ndk_path=None 崩)
rm -f "$STAGE/pysidedeploy.spec" "$STAGE/buildozer.spec"

# 删旧 APK, 否则下面 find 可能拷到陈旧化石; 构建后只取比此刻更新的
find "$STAGE" -name "*.apk" -delete
BUILD_MARKER="$STAGE/.build_marker"
touch "$BUILD_MARKER"

# app 纯 Python 依赖逐个列全(p4a 用 --no-deps, 否则 auto-resolver 遇无 android wheel 的包会崩);
# jh2 有 recipe 交叉编译、gd3ffmpeg 走预置 jniLibs; 跳过 orjson(stdlib shim 兜)/desktop-notifier/uvloop 等。
# deploy patch 把 GD3_EXTRA_REQ 追加到 requirements、GD3_EXTRA_PERM 到 permissions。
export GD3_EXTRA_REQ="${GD3_EXTRA_REQ:-,pyjnius,niquests,urllib3-future,charset-normalizer,idna,h11,wassima,jh2,PySide6-Fluent-Widgets,PySideSix-Frameless-Window,darkdetect,loguru,qrcode,pypng,m3u8,mpegdash,aioftp,gd3ffmpeg}"
export GD3_EXTRA_PERM="${GD3_EXTRA_PERM:-,MANAGE_EXTERNAL_STORAGE,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS}"
# 启动器图标改指仓库 logo.png(deploy 默认 PySide6 python logo)
export GD3_ICON="${GD3_ICON:-$REPO/app/assets/logo.png}"
# adaptive icon(消 API26+ 白边)+ presplash(冷启动图), 资源由 make_launch_assets.py 从 logo.png 派生
export GD3_ICON_FG="${GD3_ICON_FG:-$ANDROID_DIR/assets/icon_foreground.png}"
export GD3_ICON_BG="${GD3_ICON_BG:-$ANDROID_DIR/assets/icon_background.png}"
export GD3_PRESPLASH="${GD3_PRESPLASH:-$ANDROID_DIR/assets/presplash.jpg}"
export GD3_PRESPLASH_COLOR="${GD3_PRESPLASH_COLOR:-#F3F3F3}"
# 注入 values-night 资源, 闪屏/windowBackground 随系统深浅(values/ 浅 + values-night/ 深)
export GD3_RES="${GD3_RES:-$ANDROID_DIR/res/values-night/colors.xml:values-night/colors.xml}"
# 正式包标识(title/package.name/package.domain 解耦, 规避带空格的 title 致 package.name 非法)
export GD3_APP_TITLE="${GD3_APP_TITLE:-Ghost Downloader}"
export GD3_PKG_NAME="${GD3_PKG_NAME:-ghostdownloader}"
export GD3_PKG_DOMAIN="${GD3_PKG_DOMAIN:-io.github.xiaoyouchr}"
# APK 版本号同步真 app VERSION(否则 buildozer 默认 0.1)
export GD3_VERSION="${GD3_VERSION:-$(grep -oP '^VERSION = "\K[^"]+' "$REPO/app/supports/config.py")}"
# 显式 Qt 模块清单(每个须在 wheel 有 Qt{X}.abi3.so, 故不列只有 C++ 库的 Core5Compat);
# 非空即让 deploy 跳过自动探测, 避免扫到桌面分支 QtDBus(Android wheel 无 libQt6DBus)崩。
export GD3_QT_MODULES="${GD3_QT_MODULES:-Core,Gui,Widgets,Network,Svg,SvgWidgets,WebSockets,Xml}"
echo "[build] STAGE=$STAGE"
echo "[build] applicationId=$GD3_PKG_DOMAIN.$GD3_PKG_NAME  label=$GD3_APP_TITLE"
echo "[build] adaptive icon fg=$GD3_ICON_FG bg=$GD3_ICON_BG  presplash=$GD3_PRESPLASH color=$GD3_PRESPLASH_COLOR"
echo "[build] GD3_EXTRA_REQ=$GD3_EXTRA_REQ  GD3_EXTRA_PERM=$GD3_EXTRA_PERM"
echo "[build] GD3_QT_MODULES=$GD3_QT_MODULES"

# 修 p4a adaptive icon bug(写 mipmap-anydpi-v26/icon.xml 前没建目录): 镜像已修, 但增量缓存里旧 build.py 未修, 就地幂等补。
# 守卫 .buildozer 存在(CI 首跑还没生成, 无守卫 find 会非零退出中断)。
if [ -d "$STAGE/.buildozer" ]; then
    find "$STAGE/.buildozer" -name "build.py" \( -path "*bootstrap_builds/qt/*" -o -path "*dists/*" \) 2>/dev/null | while read -r buildPy; do
        if grep -q "mipmap-anydpi-v26/icon.xml" "$buildPy" && ! grep -q 'ensure_dir(join(res_dir, "mipmap-anydpi-v26"))' "$buildPy"; then
            sed -i 's#^\( *\)with open(join(res_dir, .mipmap-anydpi-v26/icon.xml.), .w.) as fd:#\1ensure_dir(join(res_dir, "mipmap-anydpi-v26"))\n&#' "$buildPy"
            echo "[build] 补 p4a adaptive icon mkdir: $buildPy"
        fi
    done
fi

PYSIDE_WHL=$(ls "$WHEEL_DIR"/PySide6-*android_aarch64.whl)
SHIBOKEN_WHL=$(ls "$WHEEL_DIR"/shiboken6-*android_aarch64.whl)
echo "[build] PySide6  wheel: $PYSIDE_WHL"
echo "[build] shiboken wheel: $SHIBOKEN_WHL"

pyside6-android-deploy -f -v \
    --name GhostDownloaderProbe \
    --wheel-pyside "$PYSIDE_WHL" \
    --wheel-shiboken "$SHIBOKEN_WHL"

mkdir -p "$ANDROID_DIR/dist"
# 只收集「比构建开始更新」的 APK（杜绝拷到陈旧化石）。deploy 写到 bin_dir(exe_dir=STAGE)。
FRESH_APK=$(find "$STAGE" -name "*.apk" -newer "$BUILD_MARKER" -printf "%T@ %p\n" 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
rm -f "$BUILD_MARKER"
if [ -z "$FRESH_APK" ]; then
    echo "[build] 错误：未找到本次新生成的 APK！" >&2
    exit 1
fi
cp -v "$FRESH_APK" "$ANDROID_DIR/dist/"

# Release 签名（可选）：设了 GD3_KEYSTORE 才签——deploy 只出 debug APK，这里 zipalign + apksigner 重签为
# release。未设则保持 debug（本地快速迭代 / fork 无密钥的 CI）。
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
    rm -f "$DEBUG_APK"  # 只留 release
fi

echo "[build] 产物（本次新构建）："
ls -la "$ANDROID_DIR/dist"
