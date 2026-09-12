#!/usr/bin/env bash
set -euo pipefail

# Cross-compile goed2kd for Android
#
# Prerequisites:
#   - Go 1.24+
#   - Android NDK (ANDROID_NDK_HOME or ANDROID_NDK_LATEST_HOME)
#   - Python-eD2k source (GOED2K_SRC or auto-detect)
#
# Usage:
#   ./build_goed2kd.sh [--abi=arm64-v8a|all]
#
# Output:
#   ../app/src/main/jniLibs/<abi>/libgoed2kd.so

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JNILIBS_DIR="${SCRIPT_DIR}/../app/src/main/jniLibs"
GOED2K_SRC="${GOED2K_SRC:-$(cd "$SCRIPT_DIR/../../.." && pwd)/Python-eD2k}"
NDK="${ANDROID_NDK_HOME:-${ANDROID_NDK_LATEST_HOME:-}}"

if [ ! -d "$NDK/toolchains/llvm/prebuilt" ]; then
    echo "ERROR: Set ANDROID_NDK_HOME to an installed Android NDK" >&2
    exit 1
fi

case "$(uname -s)" in
    Darwin) HOST_TAG="darwin-x86_64" ;;
    Linux)  HOST_TAG="linux-x86_64" ;;
    *) echo "ERROR: Unsupported build host" >&2; exit 1 ;;
esac

if [ ! -f "$GOED2K_SRC/go.mod" ]; then
    echo "ERROR: Python-eD2k source not found at $GOED2K_SRC" >&2
    echo "Set GOED2K_SRC to the Python-eD2k repo root" >&2
    exit 1
fi

TARGET_ABIS="${1:---abi=arm64-v8a}"
case "$TARGET_ABIS" in
    --abi=all|all)  ABIS="arm64-v8a" ;;
    --abi=*)        ABIS="${TARGET_ABIS#--abi=}" ;;
    *)              ABIS="$TARGET_ABIS" ;;
esac

buildAbi() {
    local ABI="$1"
    local GOARCH TRIPLET
    case "$ABI" in
        arm64-v8a) GOARCH="arm64"; TRIPLET="aarch64-linux-android" ;;
        x86_64)    GOARCH="amd64"; TRIPLET="x86_64-linux-android" ;;
        *) echo "ERROR: Unsupported ABI: $ABI" >&2; exit 1 ;;
    esac
    # API 28 matches the Compose app's minimum SDK.
    local COMPILER="$NDK/toolchains/llvm/prebuilt/$HOST_TAG/bin/${TRIPLET}28-clang"
    if [ ! -x "$COMPILER" ]; then
        echo "ERROR: NDK compiler not found: $COMPILER" >&2
        exit 1
    fi
    local OUT="$JNILIBS_DIR/$ABI/libgoed2kd.so"

    local VERSION
    VERSION="$(git -C "$GOED2K_SRC" describe --tags --always 2>/dev/null || echo "dev")"

    echo "Building goed2kd ${VERSION} ($ABI)..."
    mkdir -p "$(dirname "$OUT")"
    # Android DNS needs the system resolver, which is unavailable without CGO.
    CGO_ENABLED=1 CC="$COMPILER" GOOS=android GOARCH="$GOARCH" \
        go build -C "$GOED2K_SRC" -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o "$OUT" ./cmd/goed2kd
    echo "  -> $(ls -lh "$OUT" | awk '{print $5}') $OUT"
}

for ABI in $ABIS; do
    buildAbi "$ABI"
done

echo ""
echo "Done."
