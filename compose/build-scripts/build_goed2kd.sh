#!/usr/bin/env bash
set -euo pipefail

# Cross-compile goed2kd for Android
#
# Prerequisites:
#   - Go 1.24+ (CGO_ENABLED=0, no NDK needed)
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

abi_to_goarch() {
    case "$1" in
        arm64-v8a) echo "arm64" ;;
        x86_64)    echo "amd64" ;;
    esac
}

build_abi() {
    local ABI="$1"
    local GOARCH="$(abi_to_goarch "$ABI")"
    local OUT="$JNILIBS_DIR/$ABI/libgoed2kd.so"

    local VERSION
    VERSION="$(git -C "$GOED2K_SRC" describe --tags --always 2>/dev/null || echo "dev")"

    echo "Building goed2kd ${VERSION} ($ABI)..."
    mkdir -p "$(dirname "$OUT")"
    CGO_ENABLED=0 GOOS=android GOARCH="$GOARCH" \
        go build -C "$GOED2K_SRC" -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o "$OUT" ./cmd/goed2kd
    echo "  -> $(ls -lh "$OUT" | awk '{print $5}') $OUT"
}

for ABI in $ABIS; do
    build_abi "$ABI"
done

echo ""
echo "Done."
