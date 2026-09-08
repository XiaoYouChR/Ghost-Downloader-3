#!/usr/bin/env bash
set -euo pipefail

# Build libtorrent Python wheel for Android (arm64-v8a + x86_64)
#
# Prerequisites:
#   - Linux x86_64 host
#   - Android NDK (ANDROID_NDK_HOME or auto-detect from ANDROID_HOME)
#   - Host Python 3.14 + wheel (pip install wheel)
#
# Usage:
#   ./build_libtorrent_wheel.sh [--abi arm64-v8a|x86_64|all]
#
# Output:
#   dist/libtorrent-<version>-cp314-cp314-android_24_<abi>.whl

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/build"
DIST_DIR="${SCRIPT_DIR}/dist"

BOOST_VERSION="1.92.0"
BOOST_UNDERSCORE="1_92_0"
OPENSSL_VERSION="3.5.5"
LIBTORRENT_VERSION="2.1.1"
CPYTHON_VERSION="3.14.7"
ANDROID_API=24
HOST_PYTHON="${BUILD_PYTHON:-$(command -v python3.14 || command -v python3)}"

TARGET_ABIS="${1:---abi=all}"
case "$TARGET_ABIS" in
    --abi=all|all)  ABIS="arm64-v8a x86_64" ;;
    --abi=*)        ABIS="${TARGET_ABIS#--abi=}" ;;
    *)              ABIS="$TARGET_ABIS" ;;
esac

abi_to_arch_triplet() {
    case "$1" in
        arm64-v8a) echo "aarch64-linux-android" ;;
        x86_64)    echo "x86_64-linux-android" ;;
    esac
}

abi_to_cpython_arch() {
    case "$1" in
        arm64-v8a) echo "aarch64" ;;
        x86_64)    echo "x86_64" ;;
    esac
}

abi_to_b2_address_model() {
    case "$1" in
        arm64-v8a) echo "64" ;;
        x86_64)    echo "64" ;;
    esac
}

abi_to_wheel_tag() {
    case "$1" in
        arm64-v8a) echo "arm64_v8a" ;;
        x86_64)    echo "x86_64" ;;
    esac
}

# --- Detect NDK ---

detect_ndk() {
    if [ -n "${ANDROID_NDK_HOME:-}" ]; then
        NDK="$ANDROID_NDK_HOME"
    elif [ -n "${ANDROID_HOME:-}" ]; then
        NDK="$(ls -d "$ANDROID_HOME/ndk/"* 2>/dev/null | sort -V | tail -1)"
    elif [ -n "${ANDROID_SDK_ROOT:-}" ]; then
        NDK="$(ls -d "$ANDROID_SDK_ROOT/ndk/"* 2>/dev/null | sort -V | tail -1)"
    else
        echo "ERROR: Set ANDROID_NDK_HOME or ANDROID_HOME" >&2
        exit 1
    fi

    if [ ! -d "$NDK/toolchains/llvm/prebuilt" ]; then
        echo "ERROR: Invalid NDK at $NDK" >&2
        exit 1
    fi

    HOST_TAG="$(ls "$NDK/toolchains/llvm/prebuilt/")"
    TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/$HOST_TAG"
    echo "NDK: $NDK (host: $HOST_TAG)"
}

# --- Download sources ---

download_sources() {
    mkdir -p "$WORK_DIR/src"
    cd "$WORK_DIR/src"

    if [ ! -d "boost_${BOOST_UNDERSCORE}" ]; then
        echo "Downloading Boost ${BOOST_VERSION}..."
        curl -fSL "https://archives.boost.io/release/${BOOST_VERSION}/source/boost_${BOOST_UNDERSCORE}.tar.gz" \
            | tar xz
    fi

    if [ ! -d "openssl-${OPENSSL_VERSION}" ]; then
        echo "Downloading OpenSSL ${OPENSSL_VERSION}..."
        curl -fSL "https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz" \
            | tar xz
    fi

    if [ ! -d "libtorrent-${LIBTORRENT_VERSION}" ]; then
        echo "Downloading libtorrent ${LIBTORRENT_VERSION}..."
        curl -fSL "https://github.com/arvidn/libtorrent/releases/download/v${LIBTORRENT_VERSION}/libtorrent-rasterbar-${LIBTORRENT_VERSION}.tar.gz" \
            | tar xz
        mv "libtorrent-rasterbar-${LIBTORRENT_VERSION}" "libtorrent-${LIBTORRENT_VERSION}"
    fi

    for abi_arch in aarch64 x86_64; do
        local dir="cpython-${CPYTHON_VERSION}-${abi_arch}"
        if [ ! -d "$dir" ]; then
            echo "Downloading CPython ${CPYTHON_VERSION} headers (${abi_arch})..."
            mkdir -p "$dir"
            curl -fSL "https://www.python.org/ftp/python/${CPYTHON_VERSION}/python-${CPYTHON_VERSION}-${abi_arch}-linux-android.tar.gz" \
                | tar xz -C "$dir"
        fi
    done
}

# --- Build OpenSSL ---

build_openssl() {
    local ABI="$1"
    local TRIPLET="$(abi_to_arch_triplet "$ABI")"
    local OUT="$WORK_DIR/openssl/$ABI"

    if [ -f "$OUT/lib/libssl.a" ]; then
        echo "OpenSSL ($ABI): already built"
        return
    fi

    echo "Building OpenSSL ($ABI)..."
    local BUILD="$WORK_DIR/openssl/build-$ABI"
    rm -rf "$BUILD"
    mkdir -p "$WORK_DIR/openssl"
    cp -R "$WORK_DIR/src/openssl-${OPENSSL_VERSION}" "$BUILD"
    cd "$BUILD"

    local ANDROID_ARCH
    case "$ABI" in
        arm64-v8a) ANDROID_ARCH="android-arm64" ;;
        x86_64)    ANDROID_ARCH="android-x86_64" ;;
    esac

    export ANDROID_NDK_ROOT="$NDK"
    export PATH="$TOOLCHAIN/bin:$PATH"

    ./Configure "$ANDROID_ARCH" \
        -D__ANDROID_API__=${ANDROID_API} \
        no-shared no-tests no-ui-console \
        --prefix="$OUT"

    make -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
    make install_sw
    cd "$WORK_DIR"
}

# --- Build Boost + Boost.Python ---

build_boost() {
    local ABI="$1"
    local TRIPLET="$(abi_to_arch_triplet "$ABI")"
    local CPYTHON_ARCH="$(abi_to_cpython_arch "$ABI")"
    local ADDR_MODEL="$(abi_to_b2_address_model "$ABI")"
    local BOOST_SRC="$WORK_DIR/src/boost_${BOOST_UNDERSCORE}"
    local OUT="$WORK_DIR/boost/$ABI"
    local PYTHON_INCLUDE="$WORK_DIR/src/cpython-${CPYTHON_VERSION}-${CPYTHON_ARCH}/prefix/include/python3.14"

    if [ -f "$OUT/stage/lib/libboost_python314.a" ]; then
        echo "Boost ($ABI): already built"
        return
    fi

    echo "Building Boost + Boost.Python ($ABI)..."

    # Bootstrap b2 (host, once)
    if [ ! -f "$BOOST_SRC/b2" ]; then
        cd "$BOOST_SRC"
        ./bootstrap.sh
        cd "$WORK_DIR"
    fi

    # Generate user-config.jam
    local JAM="$OUT/user-config.jam"
    local PYTHON_LIB="$WORK_DIR/src/cpython-${CPYTHON_VERSION}-${CPYTHON_ARCH}/prefix/lib"
    mkdir -p "$OUT"
    cat > "$JAM" <<JAMEOF
using clang : android
  : ${TOOLCHAIN}/bin/${TRIPLET}${ANDROID_API}-clang++
  : <archiver>${TOOLCHAIN}/bin/llvm-ar
    <ranlib>${TOOLCHAIN}/bin/llvm-ranlib
  ;

using python : 3.14
  :
  : ${PYTHON_INCLUDE}
  : ${PYTHON_LIB}
  : <target-os>android
  ;
JAMEOF

    cd "$BOOST_SRC"
    ./b2 -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)" -a -q \
        --ignore-site-config \
        --user-config="$JAM" \
        --build-dir="$OUT/build" \
        --stagedir="$OUT/stage" \
        --with-python --with-system \
        toolset=clang-android \
        target-os=android \
        link=static \
        threading=multi \
        address-model="$ADDR_MODEL" \
        cxxstd=17 \
        cxxflags=-fPIC \
        variant=release \
        stage

    cd "$WORK_DIR"
}

# --- Build libtorrent + Python binding ---

build_libtorrent() {
    local ABI="$1"
    local CPYTHON_ARCH="$(abi_to_cpython_arch "$ABI")"
    local BUILD="$WORK_DIR/libtorrent/build-$ABI"
    local PYTHON_PREFIX="$WORK_DIR/src/cpython-${CPYTHON_VERSION}-${CPYTHON_ARCH}/prefix"

    if [ -d "$BUILD" ] && ls "$BUILD"/bindings/python/libtorrent*.so >/dev/null 2>&1; then
        echo "libtorrent ($ABI): already built"
        return
    fi

    echo "Building libtorrent + Python binding ($ABI)..."

    # setup-python sets Python3_ROOT_DIR to the host x86_64 Python.
    # Unset so CMake uses our explicit ARM64 Android paths instead.
    unset Python3_ROOT_DIR Python_ROOT_DIR Python2_ROOT_DIR

    cmake -B "$BUILD" \
        -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
        -DANDROID_ABI="$ABI" \
        -DANDROID_PLATFORM="android-${ANDROID_API}" \
        -DANDROID_STL=c++_static \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHARED_LIBS=OFF \
        -DCMAKE_POLICY_DEFAULT_CMP0144=OLD \
        -DCMAKE_POLICY_DEFAULT_CMP0167=OLD \
        -Dpython-bindings=ON \
        -Dpython-egg-info=OFF \
        -DPython3_EXECUTABLE="$HOST_PYTHON" \
        -DPython3_INCLUDE_DIR="$PYTHON_PREFIX/include/python3.14" \
        -DPython3_LIBRARY="$PYTHON_PREFIX/lib/libpython3.14.so" \
        -DPython3_FIND_STRATEGY=LOCATION \
        -DPython3_FIND_REGISTRY=NEVER \
        -DPython3_FIND_FRAMEWORK=NEVER \
        -DBOOST_ROOT="$WORK_DIR/src/boost_${BOOST_UNDERSCORE}" \
        -DBoost_INCLUDE_DIR="$WORK_DIR/src/boost_${BOOST_UNDERSCORE}" \
        -DBOOST_LIBRARYDIR="$WORK_DIR/boost/$ABI/stage/lib" \
        -DBoost_LIBRARY_DIR="$WORK_DIR/boost/$ABI/stage/lib" \
        -DBoost_NO_SYSTEM_PATHS=ON \
        -DBoost_NO_BOOST_CMAKE=ON \
        -DOPENSSL_ROOT_DIR="$WORK_DIR/openssl/$ABI" \
        -DOPENSSL_INCLUDE_DIR="$WORK_DIR/openssl/$ABI/include" \
        -DOPENSSL_CRYPTO_LIBRARY="$WORK_DIR/openssl/$ABI/lib/libcrypto.a" \
        -DOPENSSL_SSL_LIBRARY="$WORK_DIR/openssl/$ABI/lib/libssl.a" \
        -DOPENSSL_USE_STATIC_LIBS=ON \
        -DCMAKE_MODULE_LINKER_FLAGS="$PYTHON_PREFIX/lib/libpython3.14.so" \
        -Dstatic_runtime=ON \
        "$WORK_DIR/src/libtorrent-${LIBTORRENT_VERSION}"

    cmake --build "$BUILD" --target python-libtorrent -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
}

# --- Package wheel ---

package_wheel() {
    local ABI="$1"
    local WHEEL_ABI_TAG="$(abi_to_wheel_tag "$ABI")"
    local BUILD="$WORK_DIR/libtorrent/build-$ABI"
    local SO_FILE="$(ls "$BUILD"/bindings/python/libtorrent*.so 2>/dev/null | head -1)"

    if [ -z "$SO_FILE" ]; then
        echo "ERROR: No .so found for $ABI" >&2
        exit 1
    fi

    local WHEEL_TAG="cp314-cp314-android_${ANDROID_API}_${WHEEL_ABI_TAG}"
    local STAGING="$WORK_DIR/wheel-$ABI"

    echo "Packaging libtorrent-${LIBTORRENT_VERSION} ($ABI)..."
    rm -rf "$STAGING"
    mkdir -p "$STAGING/libtorrent" "$STAGING/libtorrent-${LIBTORRENT_VERSION}.dist-info"

    cp "$SO_FILE" "$STAGING/libtorrent/__init__.so"
    "$TOOLCHAIN/bin/llvm-strip" "$STAGING/libtorrent/__init__.so"

    cat > "$STAGING/libtorrent-${LIBTORRENT_VERSION}.dist-info/METADATA" <<EOF
Metadata-Version: 2.4
Name: libtorrent
Version: ${LIBTORRENT_VERSION}
Summary: Python bindings for libtorrent-rasterbar
Home-page: https://libtorrent.org
License: BSD-3-Clause
EOF

    cat > "$STAGING/libtorrent-${LIBTORRENT_VERSION}.dist-info/WHEEL" <<EOF
Wheel-Version: 1.0
Generator: build_libtorrent_wheel.sh
Root-Is-Purelib: false
Tag: ${WHEEL_TAG}
EOF

    mkdir -p "$DIST_DIR"
    "$HOST_PYTHON" -m wheel pack "$STAGING" --dest-dir "$DIST_DIR"
}

# --- Main ---

detect_ndk
download_sources

for ABI in $ABIS; do
    echo ""
    echo "========== Building for $ABI =========="
    build_openssl "$ABI"
    build_boost "$ABI"
    build_libtorrent "$ABI"
    package_wheel "$ABI"
done

echo ""
echo "Done. Wheels:"
ls -la "$DIST_DIR"/*.whl
