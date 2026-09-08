#!/usr/bin/env bash
set -euo pipefail

# Patch wreq Android wheel for Chaquopy
#
# Three fixes applied to PyPI's original wheel:
#   1. DT_NEEDED: add libpython3.14.so (Android isolated linker namespaces
#      don't use RTLD_GLOBAL — CPython symbols invisible without it)
#   2. Type stubs: remove wreq.py/redirect.py/blocking.py (they shadow the
#      native .so submodules on Chaquopy, causing circular import)
#
# Not handled here (see jniLibs/ in app module):
#   3. libc++_shared.so: wreq.abi3.so links it dynamically, maturin sets
#      RPATH (Android ignores RPATH) → copy from NDK to jniLibs/{abi}/
#
# Usage:
#   ./patch_wreq_wheel.sh [--abi=arm64-v8a|x86_64|all]
#
# Output:
#   dist/wreq-<version>-<tag>.whl

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist"

WREQ_VERSION="0.12.1"
LIBPYTHON="libpython3.14.so"
ANDROID_API=24
HOST_PYTHON="${BUILD_PYTHON:-$(command -v python3.14 || command -v python3)}"

TARGET_ABIS="${1:---abi=all}"
case "$TARGET_ABIS" in
    --abi=all|all)  ABIS="arm64-v8a x86_64" ;;
    --abi=*)        ABIS="${TARGET_ABIS#--abi=}" ;;
    *)              ABIS="$TARGET_ABIS" ;;
esac

abi_to_wheel_tag() {
    case "$1" in
        arm64-v8a) echo "arm64_v8a" ;;
        x86_64)    echo "x86_64" ;;
    esac
}

patch_abi() {
    local ABI="$1"
    local WHEEL_ABI_TAG="$(abi_to_wheel_tag "$ABI")"
    local PLATFORM="android_${ANDROID_API}_${WHEEL_ABI_TAG}"
    local WORK_DIR
    WORK_DIR="$(mktemp -d)"
    trap "rm -rf '$WORK_DIR'" RETURN

    echo "Downloading wreq ${WREQ_VERSION} (${ABI}) from PyPI..."
    "$HOST_PYTHON" -m pip download \
        --only-binary=:all: \
        --platform "$PLATFORM" \
        --abi abi3 \
        --no-deps \
        -d "$WORK_DIR" \
        "wreq==${WREQ_VERSION}"

    local WHL
    WHL="$(ls "$WORK_DIR"/wreq-*.whl)"
    echo "Downloaded: $(basename "$WHL")"

    echo "Unpacking..."
    "$HOST_PYTHON" -m wheel unpack -d "$WORK_DIR/unpacked" "$WHL"
    local UNPACKED
    UNPACKED="$(ls -d "$WORK_DIR/unpacked"/wreq-*)"

    local SO="$UNPACKED/wreq/wreq.abi3.so"
    if [ ! -f "$SO" ]; then
        echo "ERROR: wreq.abi3.so not found in wheel" >&2
        exit 1
    fi

    echo "Patching DT_NEEDED: adding ${LIBPYTHON}..."
    "$HOST_PYTHON" -c "
import sys
try:
    import lief
except ImportError:
    print('ERROR: lief not installed. Run: pip install lief', file=sys.stderr)
    sys.exit(1)

binary = lief.ELF.parse('${SO}')
needed = [e.name for e in binary.dynamic_entries if isinstance(e, lief.ELF.DynamicEntryLibrary)]
if '${LIBPYTHON}' in needed:
    print('Already has ${LIBPYTHON}, skipping')
    sys.exit(0)
binary.add_library('${LIBPYTHON}')
binary.write('${SO}')
print('Added ${LIBPYTHON} to DT_NEEDED')
"

    echo "Removing type stubs that shadow native submodules..."
    rm -f "$UNPACKED/wreq/wreq.py" "$UNPACKED/wreq/redirect.py" "$UNPACKED/wreq/blocking.py"

    echo "Repacking..."
    mkdir -p "$DIST_DIR"
    "$HOST_PYTHON" -m wheel pack "$UNPACKED" --dest-dir "$DIST_DIR"
}

for ABI in $ABIS; do
    echo ""
    echo "========== Patching wreq for $ABI =========="
    patch_abi "$ABI"
done

echo ""
echo "Done. Wheels:"
ls -la "$DIST_DIR"/wreq-*.whl
