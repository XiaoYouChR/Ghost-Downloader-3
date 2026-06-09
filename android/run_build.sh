#!/usr/bin/env bash
# 在 host（WSL）执行：构建工具链镜像并在容器内打 APK。
# 构建产物落到 android/dist/*.apk；随后用 `adb install -r android/dist/*.apk` 装机。
#
# 网络策略（local == CI 同一 Dockerfile，差异只在传参）：
#   - 镜像构建：apt/pip/qt/rust 默认官方源；设 GD3_CN_MIRROR=1 改用国内镜像直连（不经代理，最快）。
#   - APK 构建容器：deploy 要从 dl.google.com 下 NDK/SDK，国内须经代理；设 HTTP_PROXY 即透传 + host 网络。
#   - NDK/SDK/buildozer 缓存用命名卷持久化，二次构建免重复下载。
set -euo pipefail

IMAGE=gd3-android-builder
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"   # 仓库根：真 app 源 app/ + features/

# --- 镜像构建参数：国内镜像源（GD3_CN_MIRROR=1 时启用）---
BUILD_ARGS=()
if [[ "${GD3_CN_MIRROR:-0}" == "1" ]]; then
    echo "[run] 启用国内镜像源构建镜像"
    BUILD_ARGS=(
        --build-arg "APT_MIRROR_HOST=mirrors.tuna.tsinghua.edu.cn"
        --build-arg "PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
        --build-arg "QT_DL=https://mirrors.ustc.edu.cn/qtproject/official_releases/QtForPython"
        --build-arg "RUSTUP_DIST_SERVER=https://mirrors.ustc.edu.cn/rust-static"
        --build-arg "RUSTUP_UPDATE_ROOT=https://mirrors.ustc.edu.cn/rust-static/rustup"
        --build-arg "P4A_GIT_URL=https://gitee.com/mirrors/python-for-android.git"
        --build-arg "FFMPEG_BASE=https://cdn.jsdelivr.net/gh/hzw1199/Android-FFmpeg-Prebuilt@main/ffmpeg-8.1.1/bin"
        --build-arg "NM3U8_URL=https://ghfast.top/https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.5.1-beta/N_m3u8DL-RE_v0.5.1-beta_android-bionic-arm64_20251029.tar.gz"
        --build-arg "GD3_GRADLE_CN=1"
    )
fi

# --- APK 构建容器参数：代理（dl.google.com 的 NDK/SDK 须走代理）---
RUN_PROXY=()
NET_HOST=()
if [[ -n "${HTTP_PROXY:-}" ]]; then
    echo "[run] 检测到 HTTP_PROXY=$HTTP_PROXY，透传给 APK 构建容器（NDK/SDK 下载用）"
    RUN_PROXY=(-e "HTTP_PROXY=$HTTP_PROXY" -e "HTTPS_PROXY=${HTTPS_PROXY:-$HTTP_PROXY}"
               -e "http_proxy=$HTTP_PROXY" -e "https_proxy=${HTTPS_PROXY:-$HTTP_PROXY}"
               -e "NO_PROXY=localhost,127.0.0.1,::1")
    NET_HOST=(--network=host)
fi

# --- Release 签名（可选）：host 设了 GD3_KEYSTORE 才挂密钥库进容器、透传口令，签为 release APK ---
SIGN_ARGS=()
if [[ -n "${GD3_KEYSTORE:-}" ]]; then
    echo "[run] 检测到 GD3_KEYSTORE，将签名为 release APK"
    SIGN_ARGS=(-v "$GD3_KEYSTORE":/tmp/release.jks:ro
               -e "GD3_KEYSTORE=/tmp/release.jks"
               -e "GD3_KEYSTORE_PASS=${GD3_KEYSTORE_PASS:-}"
               -e "GD3_KEY_ALIAS=${GD3_KEY_ALIAS:-}"
               -e "GD3_KEY_PASS=${GD3_KEY_PASS:-}")
fi

echo "[run] 构建镜像 $IMAGE ..."
docker build "${BUILD_ARGS[@]}" -t "$IMAGE" "$HERE"

# 容器内以 builder(uid 1000) 跑，但 CI runner 的 checkout 属主非 1000，builder 在挂载的 /work 下
# mkdir dist 会 Permission denied。由宿主(/work 属主)先建好 dist 并放开写权限，容器再往里写产物。
mkdir -p "$HERE/dist" && chmod 777 "$HERE/dist"

echo "[run] 容器内构建 APK ..."
docker run --rm "${NET_HOST[@]}" "${RUN_PROXY[@]}" "${SIGN_ARGS[@]}" \
    -v "$HERE":/work \
    -v "$REPO_ROOT":/repo:ro \
    -v gd3-app-stage:/home/builder/stage \
    -v gd3-pyside-android-cache:/home/builder/.pyside6_android_deploy \
    -v gd3-buildozer-cache:/home/builder/.buildozer \
    -v gd3-gradle-cache:/home/builder/.gradle \
    "$IMAGE" bash /work/build_apk.sh

echo "[run] 完成。装机命令："
echo "      adb install -r $HERE/dist/*.apk"
