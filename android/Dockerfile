FROM python:3.11-bookworm

ARG APT_MIRROR_HOST=deb.debian.org
ARG PIP_INDEX=https://pypi.org/simple
ARG QT_DL=https://download.qt.io/official_releases/QtForPython
ARG RUSTUP_DIST_SERVER=https://static.rust-lang.org
ARG RUSTUP_UPDATE_ROOT=https://static.rust-lang.org/rustup

ENV DEBIAN_FRONTEND=noninteractive \
    PYSIDE_VERSION=6.10.2 \
    PIP_INDEX_URL=${PIP_INDEX} \
    RUSTUP_DIST_SERVER=${RUSTUP_DIST_SERVER} \
    RUSTUP_UPDATE_ROOT=${RUSTUP_UPDATE_ROOT}

RUN sed -i "s|deb.debian.org|${APT_MIRROR_HOST}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        openjdk-17-jdk-headless \
        build-essential ccache git zip unzip wget curl file \
        autoconf automake libtool libtool-bin pkg-config \
        cmake \
        zlib1g-dev libffi-dev libssl-dev libncurses-dev \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH="/opt/cargo/bin:${PATH}"
RUN curl --proto '=https' --tlsv1.2 -sSf "${RUSTUP_UPDATE_ROOT}/dist/x86_64-unknown-linux-gnu/rustup-init" -o /tmp/rustup-init \
    && chmod +x /tmp/rustup-init \
    && /tmp/rustup-init -y --no-modify-path --default-toolchain stable \
    && rm /tmp/rustup-init \
    && rustup target add aarch64-linux-android \
    && chmod -R a+rX /opt/rustup /opt/cargo

RUN pip install --no-cache-dir --timeout 300 --retries 10 \
        "PySide6==${PYSIDE_VERSION}" \
        "buildozer==1.5.0" \
        "cython==0.29.33" \
        jinja2 pkginfo tqdm "packaging==24.1"

RUN DEPLOY_BZ=/usr/local/lib/python3.11/site-packages/PySide6/scripts/deploy_lib/android/buildozer.py \
    && DEPLOY_CFG=/usr/local/lib/python3.11/site-packages/PySide6/scripts/deploy_lib/android/android_config.py \
    && DEPLOY_UTIL=/usr/local/lib/python3.11/site-packages/PySide6/scripts/deploy_lib/deploy_util.py \
    && DEPLOY_AND=/usr/local/lib/python3.11/site-packages/PySide6/scripts/android_deploy.py \
    && sed -i 's|modls = self.get_value("qt", "modules")|modls = __import__("os").environ.get("GD3_QT_MODULES", "") or self.get_value("qt", "modules")|' "$DEPLOY_CFG" \
    && grep -q 'GD3_QT_MODULES' "$DEPLOY_CFG" && echo "[patch] GD3_QT_MODULES 注入 OK" \
    && sed -i 's|"requirements", "python3,shiboken6,PySide6"|"requirements", "python3==3.11.15,hostpython3==3.11.15,shiboken6,PySide6" + __import__("os").environ.get("GD3_EXTRA_REQ", "")|' "$DEPLOY_BZ" \
    && grep -q 'python3==3.11.15' "$DEPLOY_BZ" && echo "[patch] python pin OK" \
    && sed -i 's|f"{include_exts},qml,js"|f"{include_exts},qml,js,toml"|' "$DEPLOY_BZ" \
    && grep -q 'qml,js,toml' "$DEPLOY_BZ" && echo "[patch] include toml OK" \
    && sed -i 's|self.set_value("app", "android.permissions", permissions)|self.set_value("app", "android.permissions", (permissions + __import__("os").environ.get("GD3_EXTRA_PERM", "")).strip(", "))|' "$DEPLOY_BZ" \
    && grep -q 'GD3_EXTRA_PERM' "$DEPLOY_BZ" && echo "[patch] env-injectable req/perm OK" \
    && sed -i 's|self.set_value("app", "p4a.branch", "develop")|self.set_value("app", "p4a.branch", "develop"); _gp = __import__("os").environ.get("GD3_P4A_SOURCE", ""); _gp and self.set_value("app", "p4a.source_dir", _gp)|' "$DEPLOY_BZ" \
    && grep -q 'GD3_P4A_SOURCE' "$DEPLOY_BZ" && echo "[patch] p4a.source_dir injectable OK" \
    && sed -i 's|shutil.rmtree(buildozer_build)|None|' "$DEPLOY_UTIL" \
    && sed -i 's|shutil.move(buildozer_build_dir, config.generated_files_path)|None|' "$DEPLOY_AND" \
    && echo "[patch] incremental build OK"

RUN mkdir -p /opt/qt-android-wheels && cd /opt/qt-android-wheels \
    && wget -q "${QT_DL}/pyside6/PySide6-6.10.2-6.10.2-cp311-cp311-android_aarch64.whl" \
    && wget -q "${QT_DL}/shiboken6/shiboken6-6.10.2-6.10.2-cp311-cp311-android_aarch64.whl" \
    && ls -la /opt/qt-android-wheels

ARG P4A_GIT_URL=https://github.com/kivy/python-for-android.git
ENV GD3_P4A_SOURCE=/opt/p4a
COPY patches/qt_pyjniusjni.c /opt/qt_pyjniusjni.c
COPY gradle-init.gradle /opt/gradle-init.gradle

COPY recipes/ /opt/gd3-recipes/
COPY patches/gd3_prune.py /opt/gd3_prune.py
RUN git clone --depth 1 -b develop "${P4A_GIT_URL}" /opt/p4a \
    && QTSRC=/opt/p4a/pythonforandroid/bootstraps/qt/build/jni/application/src \
    && cp /opt/qt_pyjniusjni.c "$QTSRC/pyjniusjni.c" \
    && sed -i 's|LOCAL_SRC_FILES := start.c|LOCAL_SRC_FILES := start.c pyjniusjni.c|' "$QTSRC/Android.mk" \
    && grep -q 'start.c pyjniusjni.c' "$QTSRC/Android.mk" && echo "[patch] qt bootstrap pyjniusjni OK" \
    && cp -r /opt/gd3-recipes/* /opt/p4a/pythonforandroid/recipes/ \
    && ls -d /opt/p4a/pythonforandroid/recipes/jh2 && echo "[patch] gd3 recipes 装入 OK" \
    && sed -i 's|pip install -U pip"|pip install -U \\"pip==24.3.1\\""|' /opt/p4a/pythonforandroid/build.py \
    && grep -q 'pip==24.3.1' /opt/p4a/pythonforandroid/build.py && echo "[patch] venv pip 钉死 24.3.1 OK" \
    && sed -i 's|--no-deps -r requirements.txt|--no-deps --no-binary charset-normalizer -r requirements.txt|' /opt/p4a/pythonforandroid/build.py \
    && grep -q 'no-binary charset-normalizer' /opt/p4a/pythonforandroid/build.py && echo "[patch] charset-normalizer 强制纯Python OK" \
    && COMMONBUILD=/opt/p4a/pythonforandroid/bootstraps/common/build/build.py \
    && sed -i 's#^\( *\)with open(join(res_dir, .mipmap-anydpi-v26/icon.xml.), .w.) as fd:#\1ensure_dir(join(res_dir, "mipmap-anydpi-v26"))\n&#' "$COMMONBUILD" \
    && grep -q 'ensure_dir(join(res_dir, "mipmap-anydpi-v26"))' "$COMMONBUILD" && echo "[patch] p4a adaptive icon mkdir fix OK" \
    && cp /opt/gd3_prune.py /opt/p4a/pythonforandroid/gd3_prune.py \
    && sed -i 's|            self.distribute_libs(arch, \[self.ctx.get_libs_dir(arch.arch)\])|            from pythonforandroid import gd3_prune as _gp; _gp.pruneQt(self.ctx.get_libs_dir(arch.arch), join(self.ctx.get_python_install_dir(arch.arch), "PySide6"), info)\n            self.distribute_libs(arch, [self.ctx.get_libs_dir(arch.arch)])|' /opt/p4a/pythonforandroid/bootstraps/qt/__init__.py \
    && grep -q 'gd3_prune' /opt/p4a/pythonforandroid/bootstraps/qt/__init__.py && echo "[patch] gd3 Qt 瘦身钩子注入 OK" \
    && QTPA=/opt/p4a/pythonforandroid/bootstraps/qt/build/src/main/java/org/kivy/android/PythonActivity.java \
    && sed -i '/protected void onActivityResult(int requestCode, int resultCode, Intent intent) {/a\        super.onActivityResult(requestCode, resultCode, intent);' "$QTPA" \
    && grep -q 'super.onActivityResult' "$QTPA" && echo "[patch] qt PythonActivity super.onActivityResult OK" \
    && sed -i '/public boolean onKeyDown(int keyCode, KeyEvent event) {/a\        if (keyCode == KeyEvent.KEYCODE_BACK) { moveTaskToBack(true); return true; }' "$QTPA" \
    && grep -q 'moveTaskToBack' "$QTPA" && echo "[patch] qt PythonActivity 返回键退后台 OK" \
    && QTSTR=/opt/p4a/pythonforandroid/bootstraps/qt/build/templates/strings.tmpl.xml \
    && sed -i '/<item name="android:windowNoTitle">true<\/item>/a\        <item name="android:windowBackground">@drawable/gd3_splash</item>\n        <item name="android:windowSplashScreenBackground">@color/gd3_splash_bg</item>' "$QTSTR" \
    && sed -i '/<resources>/a\    <color name="gd3_splash_bg">#f3f3f3</color>' "$QTSTR" \
    && grep -q 'windowSplashScreenBackground' "$QTSTR" && echo "[patch] qt native SplashScreen(API31 windowSplashScreen) OK" \
    && chmod -R a+rX /opt/p4a

# Minimal LGPL FFmpeg from our own build repo (~3MB tarball with ffmpeg+ffprobe),
# replacing hzw1199's full build (~30MB). Pinned to a tag for reproducible APKs;
# bump the tag to update. See https://github.com/XiaoYouChR/Ghost-Downloader-FFmpeg
ARG FFMPEG_TARBALL=https://github.com/XiaoYouChR/Ghost-Downloader-FFmpeg/releases/download/n8.1.2-gd1/ffmpeg-android-arm64.tar.gz
ARG NM3U8_URL=https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.5.1-beta/N_m3u8DL-RE_v0.5.1-beta_android-bionic-arm64_20251029.tar.gz
RUN mkdir -p /opt/gd3-ffmpeg && cd /opt/gd3-ffmpeg \
    && wget -q "${FFMPEG_TARBALL}" -O /tmp/ffmpeg.tar.gz \
    && tar -xzf /tmp/ffmpeg.tar.gz -C /tmp \
    && cp /tmp/ffmpeg /opt/gd3-ffmpeg/libffmpeg.so \
    && cp /tmp/ffprobe /opt/gd3-ffmpeg/libffprobe.so \
    && rm -f /tmp/ffmpeg.tar.gz /tmp/ffmpeg /tmp/ffprobe \
    && wget -q "${NM3U8_URL}" -O /tmp/nm3u8.tar.gz \
    && tar -xzf /tmp/nm3u8.tar.gz -C /tmp \
    && cp /tmp/N_m3u8DL-RE /opt/gd3-ffmpeg/libnm3u8dlre.so \
    && rm -f /tmp/nm3u8.tar.gz /tmp/N_m3u8DL-RE \
    && chmod a+rx libffmpeg.so libffprobe.so libnm3u8dlre.so \
    && ls -la /opt/gd3-ffmpeg \
    && file libffmpeg.so | grep -q "ARM aarch64" && echo "[ffmpeg] minimal arm64 预置 OK" \
    && file libnm3u8dlre.so | grep -q "ARM aarch64" && echo "[nm3u8] bionic arm64 预置 OK"

RUN DEPLOY_BASECFG=/usr/local/lib/python3.11/site-packages/PySide6/scripts/deploy_lib/config.py \
    && DEPLOY_BZ=/usr/local/lib/python3.11/site-packages/PySide6/scripts/deploy_lib/android/buildozer.py \
    && sed -i 's|config_icon = self.get_value("app", "icon")|config_icon = __import__("os").environ.get("GD3_ICON", "") or self.get_value("app", "icon")|' "$DEPLOY_BASECFG" \
    && grep -q 'GD3_ICON' "$DEPLOY_BASECFG" && echo "[patch] GD3_ICON 注入 OK" \
    && sed -i 's|        self.set_value("app", "icon.filename", pysidedeploy_config.icon)|&\n        self.set_value("app", "icon.adaptive_foreground.filename", __import__("os").environ.get("GD3_ICON_FG", ""), raise_warning=False)\n        self.set_value("app", "icon.adaptive_background.filename", __import__("os").environ.get("GD3_ICON_BG", ""), raise_warning=False)\n        self.set_value("app", "android.add_resources", __import__("os").environ.get("GD3_RES", ""), raise_warning=False)|' "$DEPLOY_BZ" \
    && grep -q 'GD3_ICON_FG' "$DEPLOY_BZ" && grep -q 'add_resources' "$DEPLOY_BZ" && echo "[patch] GD3 adaptive icon + add_resources 注入 OK" \
    && sed -i 's|"title", pysidedeploy_config.title)|"title", __import__("os").environ.get("GD3_APP_TITLE", "") or pysidedeploy_config.title)|' "$DEPLOY_BZ" \
    && sed -i 's|"package.name", pysidedeploy_config.title)|"package.name", __import__("os").environ.get("GD3_PKG_NAME", "") or pysidedeploy_config.title)|' "$DEPLOY_BZ" \
    && sed -i 's|f"org.{pysidedeploy_config.title}")|(__import__("os").environ.get("GD3_PKG_DOMAIN", "") or f"org.{pysidedeploy_config.title}"))|' "$DEPLOY_BZ" \
    && grep -q 'GD3_APP_TITLE' "$DEPLOY_BZ" && grep -q 'GD3_PKG_NAME' "$DEPLOY_BZ" && grep -q 'GD3_PKG_DOMAIN' "$DEPLOY_BZ" && echo "[patch] GD3 包名/显示名注入 OK"

ARG GD3_GRADLE_CN=0
RUN useradd -m -u 1000 builder \
    && mkdir -p /home/builder/.pyside6_android_deploy /home/builder/.buildozer /home/builder/.gradle /home/builder/stage \
    && if [ "$GD3_GRADLE_CN" = "1" ]; then cp /opt/gradle-init.gradle /home/builder/.gradle/init.gradle; fi \
    && chown -R builder:builder /home/builder \
    && chown builder:builder /opt/p4a

RUN QTSTR=/opt/p4a/pythonforandroid/bootstraps/qt/build/templates/strings.tmpl.xml \
    && sed -i '/<item name="android:windowSplashScreenBackground">@color\/gd3_splash_bg<\/item>/a\        <item name="android:windowDrawsSystemBarBackgrounds">true</item>\n        <item name="android:statusBarColor">@color/gd3_splash_bg</item>\n        <item name="android:windowLightStatusBar">@bool/gd3_light_status_bar</item>' "$QTSTR" \
    && sed -i '/<color name="gd3_splash_bg">#f3f3f3<\/color>/a\    <bool name="gd3_light_status_bar">true</bool>' "$QTSTR" \
    && grep -q 'statusBarColor' "$QTSTR" \
    && chown builder:builder "$QTSTR" \
    && echo "[patch] qt 状态栏沉浸 statusBarColor+windowLightStatusBar OK"

RUN DEPLOY_BZ=/usr/local/lib/python3.11/site-packages/PySide6/scripts/deploy_lib/android/buildozer.py \
    && sed -i '/self.set_value("app", "title",/a\        self.set_value("app", "version", __import__("os").environ.get("GD3_VERSION", "") or "0.1")\n        self.set_value("app", "android.accept_sdk_license", "True")\n        self.set_value("buildozer", "log_level", "1")' "$DEPLOY_BZ" \
    && grep -q 'GD3_VERSION' "$DEPLOY_BZ" && grep -q 'accept_sdk_license' "$DEPLOY_BZ" && grep -q 'log_level' "$DEPLOY_BZ" && echo "[patch] GD3_VERSION + accept_sdk_license + log_level=1 注入 OK"

COPY java/org/ghostdownloader/KeepAliveService.java /opt/p4a/pythonforandroid/bootstraps/common/build/src/main/java/org/ghostdownloader/KeepAliveService.java
RUN QTMAN=/opt/p4a/pythonforandroid/bootstraps/qt/build/templates/AndroidManifest.tmpl.xml \
    && sed -i '/<\/application>/i\        <service android:name="org.ghostdownloader.KeepAliveService" android:exported="false" android:foregroundServiceType="dataSync" />' "$QTMAN" \
    && sed -i '0,/<\/activity>/{s##            <meta-data android:name="android.app.background_running" android:value="true" />\n        </activity>#}' "$QTMAN" \
    && grep -q 'KeepAliveService' "$QTMAN" \
    && grep -q 'background_running' "$QTMAN" \
    && chown -R builder:builder /opt/p4a/pythonforandroid/bootstraps/common/build/src/main/java/org/ghostdownloader \
    && echo "[patch] KeepAliveService + background_running(后台事件循环不挂起) 注入 OK"

# 隔离的新版 cmake 专供 wreq 的 btls-sys/BoringSSL（系统 cmake 3.25 在 NDK toolchain 下 FindThreads 会炸）
RUN python3 -m venv /opt/cmake4 \
    && for i in 1 2 3 4 5; do /opt/cmake4/bin/pip install --no-cache-dir --timeout 300 --retries 10 "cmake>=4.0" && break || sleep 5; done \
    && /opt/cmake4/bin/cmake --version

USER builder
WORKDIR /work
