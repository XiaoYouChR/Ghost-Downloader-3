#!/usr/bin/env bash
# 在容器内执行：用 pyside6-android-deploy 把真 app 打成 aarch64 APK。
# NDK/SDK 由 deploy 工具自动下载到 ~/.pyside6_android_deploy（通过挂载卷缓存）。
set -euo pipefail

WHEEL_DIR=/opt/qt-android-wheels
ANDROID_DIR=/work             # android/ 构建基础设施（脚本/patches/spec 模板/dist 输出）
REPO=/repo                    # 仓库根（只读挂载）：真 app 源 app/ + features/
STAGE=/home/builder/stage     # 干净的打包工程目录（持久卷，保留 .buildozer 增量）

# --- 组装打包工程：只放真 app 该进 APK 的东西（main.py + app/ + features/）---
# buildozer source.dir=. 递归打包 cwd 下匹配扩展名的文件，故工程目录必须干净（混入的
# 构建脚本/patches 的 *.py 会被当 app 代码打进 APK）。另起 STAGE，每次从 /repo 全量同步删旧。
mkdir -p "$STAGE"
rm -rf "$STAGE/app" "$STAGE/features"
cp -a "$REPO/app" "$STAGE/app"
cp -a "$REPO/features" "$STAGE/features"
cp -a "$ANDROID_DIR/main.py" "$STAGE/main.py"
# bittorrent_pack 已砍（libtorrent C++ 无 Android wheel）：不打包，免 FeatureService 加载报错噪音
rm -rf "$STAGE/features/bittorrent_pack"
# jack_yao（资源下载）移动端不做：本就是 deploy.py FEATURE_PACK_BLACKLIST 成员，不打包免加第 3 tab
rm -rf "$STAGE/features/jack_yao"
# 清掉源里带来的 __pycache__（仅 app/features，别碰 .buildozer 增量缓存），避免 stale .pyc
find "$STAGE/app" "$STAGE/features" -name "__pycache__" -type d -prune -exec rm -rf {} +

cd "$STAGE"

# 删净上次生成式配置，让 deploy 每次 fresh 生成：唯此 deploy 才会从缓存自动解析
# ndk_path/recipe_dir（spec 存在时反而跳过解析致 ndk_path=None 崩）。Qt 模块清单不靠 spec
# （Config.__init__ 的 `self.modules=[]` 会抹空），改用下面 GD3_QT_MODULES 环境变量注入。
rm -f "$STAGE/pysidedeploy.spec" "$STAGE/buildozer.spec"

# 删净所有旧 APK（含 deploy 上次产到工程根的化石），否则下面 find 可能拷到陈旧 APK
# 导致一直装旧代码。构建后只取比此刻更新的 APK。
find "$STAGE" -name "*.apk" -delete
BUILD_MARKER="$STAGE/.build_marker"
touch "$BUILD_MARKER"

# 注入 app 永久依赖。p4a 装包用 --no-deps（auto-resolver 遇无 android wheel 的包会崩），
# 故纯 Python 依赖必须逐个列全：
#   - pyjnius：JNI 取系统服务 / 拉权限 Intent；
#   - HTTP 栈：niquests + urllib3-future + 纯 Python 依赖（charset-normalizer/idna/h11/
#     wassima）+ jh2（HTTP/2 硬依赖，有 recipe 交叉编译）。qh3(HTTP/3) v1 缓做，运行时优雅降级。
#   - 真 app UI/逻辑纯 Python 依赖：qfluentwidgets(=PySide6-Fluent-Widgets) 及其传递依赖
#     (PySideSix-Frameless-Window/darkdetect)、loguru、qrcode+pypng(bili 登录二维码)、
#     m3u8、mpegdash(m3u8_pack 解析)、aioftp(ftp_pack)。
#   跳过：orjson(Rust 扩展，main.py 用 stdlib json shim 兜)、desktop-notifier(无 Android 后端，
#     core_service 已绕)、uvloop/winloop/pyobjc/nuitka/libtorrent(平台限定/已砍)。
# gd3ffmpeg：预置 bionic ffmpeg/ffprobe/N_m3u8DL-RE 二进制走 jniLibs（S5b/S5c）。
# deploy_lib 的 patch 会把 GD3_EXTRA_REQ 追加到 requirements、GD3_EXTRA_PERM 到 permissions。
export GD3_EXTRA_REQ="${GD3_EXTRA_REQ:-,pyjnius,niquests,urllib3-future,charset-normalizer,idna,h11,wassima,jh2,PySide6-Fluent-Widgets,PySideSix-Frameless-Window,darkdetect,loguru,qrcode,pypng,m3u8,mpegdash,aioftp,gd3ffmpeg}"
export GD3_EXTRA_PERM="${GD3_EXTRA_PERM:-,MANAGE_EXTERNAL_STORAGE}"
# app 启动器图标：deploy 默认用 PySide6 自带 python logo，改指仓库 logo.png（Dockerfile 已 patch
# config.py 优先读 GD3_ICON）。buildozer/p4a 从这张 1024² PNG 生成各密度 mipmap。
export GD3_ICON="${GD3_ICON:-$REPO/app/assets/logo.png}"
# adaptive icon(API26+ 消桌面白边) + 冷启动 presplash(换掉默认 Kivy "Loading..." 黑底图)：
# 资源由 android/make_launch_assets.py 从 logo.png 派生、提交在 android/assets(=/work/assets)。
# Dockerfile 已 patch buildozer.py 把这四键解耦读下列环境变量。presplash 底色取浅色主窗背景, 衔接无跳色。
export GD3_ICON_FG="${GD3_ICON_FG:-$ANDROID_DIR/assets/icon_foreground.png}"
export GD3_ICON_BG="${GD3_ICON_BG:-$ANDROID_DIR/assets/icon_background.png}"
export GD3_PRESPLASH="${GD3_PRESPLASH:-$ANDROID_DIR/assets/presplash.jpg}"
export GD3_PRESPLASH_COLOR="${GD3_PRESPLASH_COLOR:-#F3F3F3}"
# 主题跟随: 注入 values-night 资源, 深色模式下 gd3_splash_bg 解析为深色 → 系统闪屏/windowBackground/
# 退出归位都跟随系统深浅(values/ 浅 + values-night/ 深, 系统按夜间模式自动选)。SRC:DEST 经 android.add_resources。
export GD3_RES="${GD3_RES:-$ANDROID_DIR/res/values-night/colors.xml:values-night/colors.xml}"
# 正式包标识：applicationId=io.github.xiaoyouchr.ghostdownloader（镜像桌面 DESKTOP_ID），
# 显示名 "Ghost Downloader"（带空格、仅 label，规避 title 带空格致 package.name 非法的坑）。
# Dockerfile 已 patch buildozer.py 把 title/package.name/package.domain 解耦读下列环境变量。
# --name 仅留作 deploy 内部 dist 句柄，用户可见标识全由这三项决定。
export GD3_APP_TITLE="${GD3_APP_TITLE:-Ghost Downloader}"
export GD3_PKG_NAME="${GD3_PKG_NAME:-ghostdownloader}"
export GD3_PKG_DOMAIN="${GD3_PKG_DOMAIN:-io.github.xiaoyouchr}"
# APK 版本号同步真 app VERSION（否则 buildozer 默认 0.1）。Dockerfile 已 patch buildozer.py 读 GD3_VERSION。
export GD3_VERSION="${GD3_VERSION:-$(grep -oP '^VERSION = "\K[^"]+' "$REPO/app/supports/config.py")}"
# 显式 Qt 模块清单 = app + qfluentwidgets 实际 import 的 Python Qt 模块。两个约束：
#   1) 每个模块必须在 wheel 里有 Qt{X}.abi3.so（PySide6 recipe 按此清单逐个复制 abi3 绑定，
#      缺一个就 FileNotFoundError）—— 故不能放 Core5Compat（只有 C++ libQt6Core5Compat.so，
#      无 Python 绑定）；它的 C++ 库由 recipe 的 copytree 全量拷入、gd3_prune keep-set 保留，无需在此列。
#   2) 非空即让 deploy 跳过源码自动探测，避免扫到 app 桌面分支的 QtDBus（Android Qt wheel 无 libQt6DBus）崩。
# DBus(桌面分支, 运行时 IS_ANDROID 绕开)、Multimedia(qfluentwidgets 顶层不加载)不列。
export GD3_QT_MODULES="${GD3_QT_MODULES:-Core,Gui,Widgets,Network,Svg,SvgWidgets,WebSockets,Xml}"
echo "[build] STAGE=$STAGE"
echo "[build] applicationId=$GD3_PKG_DOMAIN.$GD3_PKG_NAME  label=$GD3_APP_TITLE"
echo "[build] adaptive icon fg=$GD3_ICON_FG bg=$GD3_ICON_BG  presplash=$GD3_PRESPLASH color=$GD3_PRESPLASH_COLOR"
echo "[build] GD3_EXTRA_REQ=$GD3_EXTRA_REQ  GD3_EXTRA_PERM=$GD3_EXTRA_PERM"
echo "[build] GD3_QT_MODULES=$GD3_QT_MODULES"

# 修 p4a adaptive icon bug（写 mipmap-anydpi-v26/icon.xml 前没建目录）。/opt/p4a 已在镜像层修好，
# 但增量构建复用缓存卷里旧 dist 的 build.py 是未修版，这里就地幂等补。
# 守卫 .buildozer 存在：CI 全新 runner 首跑时它还没生成，无守卫的 find 会非零退出（set -e+pipefail）而中断。
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
