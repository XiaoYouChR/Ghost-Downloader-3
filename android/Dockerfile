# Ghost Downloader 3 —— Android 构建工具链镜像。本地 == CI 跑同一镜像; 容器只构建 APK, adb 装机在 host。
# 镜像源参数化(默认官方, 国内经 build-arg 传镜像, run_build.sh 自动传)。
# 关键约束: Qt Android wheel 是 cp311 专用 → host Python 必须 3.11; buildozer==1.5.0/cython==0.29.33 是 deploy 锁定版本。
FROM python:3.11-bookworm

# --- 镜像源参数（默认官方，本地传国内）---
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

# --- 系统层：换 apt 镜像 + JDK17 + p4a/buildozer 构建依赖 ---
RUN sed -i "s|deb.debian.org|${APT_MIRROR_HOST}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        openjdk-17-jdk-headless \
        build-essential ccache git zip unzip wget curl file \
        autoconf automake libtool libtool-bin pkg-config \
        cmake \
        zlib1g-dev libffi-dev libssl-dev libncurses-dev \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

# --- Rust 交叉编译链（系统级安装到 /opt，非 root 用户也能用；为 S4 的 Rust recipe 预备）---
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH="/opt/cargo/bin:${PATH}"
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path --default-toolchain stable \
    && rustup target add aarch64-linux-android \
    && chmod -R a+rX /opt/rustup /opt/cargo

# --- Python 层：PySide6 host 工具（提供 pyside6-android-deploy）+ buildozer 栈 ---
RUN pip install --no-cache-dir \
        "PySide6==${PYSIDE_VERSION}" \
        "buildozer==1.5.0" \
        "cython==0.29.33" \
        jinja2 pkginfo tqdm "packaging==24.1"

# patch pyside6-android-deploy(写死项改为可经 GD3_* 环境变量注入):
#  - 钉死 Python 3.11.15(p4a 默认拉 3.14 与 cp311 wheel 不匹配)
#  - GD3_EXTRA_REQ/PERM 追加 requirements/permissions; include_exts 加 toml(否则 manifest.toml 不进 APK)
#  - 增量构建: 不删 /work/.buildozer, 复用已编 CPython
#  - GD3_QT_MODULES 注入 Qt 模块清单: deploy 自动扫描会扫到桌面分支 QtDBus(Android 无)崩、且漏 qfluentwidgets 用的模块
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
    && sed -i 's|shutil.rmtree(buildozer_build)|None  # GD3 keep .buildozer for incremental|' "$DEPLOY_UTIL" \
    && sed -i 's|shutil.move(buildozer_build_dir, config.generated_files_path)|None  # GD3 keep .buildozer in place|' "$DEPLOY_AND" \
    && echo "[patch] incremental build OK"

# --- 烘焙 Qt 的 aarch64 Android wheel（避免每次构建重新下载 ~200MB）---
RUN mkdir -p /opt/qt-android-wheels && cd /opt/qt-android-wheels \
    && wget -q "${QT_DL}/pyside6/PySide6-6.10.2-6.10.2-cp311-cp311-android_aarch64.whl" \
    && wget -q "${QT_DL}/shiboken6/shiboken6-6.10.2-6.10.2-cp311-cp311-android_aarch64.whl" \
    && ls -la /opt/qt-android-wheels

# 本地 p4a(/opt/p4a, deploy 经 GD3_P4A_SOURCE 用它): qt bootstrap 的 libmain 只编 start.c, 缺
# pyjnius 要的 WebView_AndroidGetJNIEnv 符号 → jnius.so dlopen 失败; 给它补编 pyjniusjni.c。
ARG P4A_GIT_URL=https://github.com/kivy/python-for-android.git
ENV GD3_P4A_SOURCE=/opt/p4a
COPY patches/qt_pyjniusjni.c /opt/qt_pyjniusjni.c
COPY gradle-init.gradle /opt/gradle-init.gradle
# 自定义 p4a recipe(塞进 recipes/ 成内置): jh2(Rust 交叉编译 HTTP/2), 否则 --only-binary 忽略。
COPY patches/recipes/ /opt/gd3-recipes/
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
    && sed -i 's|            self.distribute_libs(arch, \[self.ctx.get_libs_dir(arch.arch)\])|            from pythonforandroid import gd3_prune as _gp; _gp.prune_qt(self.ctx.get_libs_dir(arch.arch), join(self.ctx.get_python_install_dir(arch.arch), "PySide6"), info)\n            self.distribute_libs(arch, [self.ctx.get_libs_dir(arch.arch)])|' /opt/p4a/pythonforandroid/bootstraps/qt/__init__.py \
    && grep -q 'gd3_prune' /opt/p4a/pythonforandroid/bootstraps/qt/__init__.py && echo "[patch] gd3 Qt 瘦身钩子注入 OK" \
    && QTPA=/opt/p4a/pythonforandroid/bootstraps/qt/build/src/main/java/org/kivy/android/PythonActivity.java \
    && sed -i '/protected void onActivityResult(int requestCode, int resultCode, Intent intent) {/a\        super.onActivityResult(requestCode, resultCode, intent);' "$QTPA" \
    && grep -q 'super.onActivityResult' "$QTPA" && echo "[patch] qt PythonActivity super.onActivityResult OK" \
    && QTSTR=/opt/p4a/pythonforandroid/bootstraps/qt/build/templates/strings.tmpl.xml \
    && sed -i '/<item name="android:windowNoTitle">true<\/item>/a\        <item name="android:windowBackground">@color/gd3_splash_bg</item>\n        <item name="android:windowSplashScreenBackground">@color/gd3_splash_bg</item>' "$QTSTR" \
    && sed -i '/<resources>/a\    <color name="gd3_splash_bg">#f3f3f3</color>' "$QTSTR" \
    && grep -q 'windowSplashScreenBackground' "$QTSTR" && echo "[patch] qt native SplashScreen(API31 windowSplashScreen) OK" \
    && chmod -R a+rX /opt/p4a

# 预置 bionic arm64 ffmpeg/ffprobe(hzw1199 8.1.1)+ N_m3u8DL-RE, 改名 lib*.so 供 gd3ffmpeg recipe
# 走 jniLibs→nativeLibraryDir→exec。image build 无 host 代理, 国内经 CDN/镜像(run_build.sh GD3_CN_MIRROR=1 传)。
ARG FFMPEG_BASE=https://raw.githubusercontent.com/hzw1199/Android-FFmpeg-Prebuilt/main/ffmpeg-8.1.1/bin
ARG NM3U8_URL=https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.5.1-beta/N_m3u8DL-RE_v0.5.1-beta_android-bionic-arm64_20251029.tar.gz
RUN mkdir -p /opt/gd3-ffmpeg && cd /opt/gd3-ffmpeg \
    && wget -q "${FFMPEG_BASE}/ffmpeg" -O libffmpeg.so \
    && wget -q "${FFMPEG_BASE}/ffprobe" -O libffprobe.so \
    && wget -q "${NM3U8_URL}" -O /tmp/nm3u8.tar.gz \
    && tar -xzf /tmp/nm3u8.tar.gz -C /tmp \
    && cp /tmp/N_m3u8DL-RE /opt/gd3-ffmpeg/libnm3u8dlre.so \
    && rm -f /tmp/nm3u8.tar.gz /tmp/N_m3u8DL-RE \
    && chmod a+rx libffmpeg.so libffprobe.so libnm3u8dlre.so \
    && ls -la /opt/gd3-ffmpeg \
    && file libffmpeg.so | grep -q "ARM aarch64" && echo "[ffmpeg] bionic arm64 预置 OK" \
    && file libnm3u8dlre.so | grep -q "ARM aarch64" && echo "[nm3u8] bionic arm64 预置 OK"

# 图标/启动图/包名经 GD3_* 环境变量注入(deploy 默认值不合用):
#  - GD3_ICON + adaptive_foreground/background(消 API26+ 桌面白边) + presplash(冷启动图)
#  - GD3_APP_TITLE/PKG_NAME/PKG_DOMAIN 解耦(deploy 默认派生丑名 org.x.x, 且带空格的 title 非法)
# 置于昂贵下载层之后, 改它只重建廉价 user-setup 层。
RUN DEPLOY_BASECFG=/usr/local/lib/python3.11/site-packages/PySide6/scripts/deploy_lib/config.py \
    && DEPLOY_BZ=/usr/local/lib/python3.11/site-packages/PySide6/scripts/deploy_lib/android/buildozer.py \
    && sed -i 's|config_icon = self.get_value("app", "icon")|config_icon = __import__("os").environ.get("GD3_ICON", "") or self.get_value("app", "icon")|' "$DEPLOY_BASECFG" \
    && grep -q 'GD3_ICON' "$DEPLOY_BASECFG" && echo "[patch] GD3_ICON 注入 OK" \
    && sed -i 's|        self.set_value("app", "icon.filename", pysidedeploy_config.icon)|&\n        self.set_value("app", "icon.adaptive_foreground.filename", __import__("os").environ.get("GD3_ICON_FG", ""), raise_warning=False)\n        self.set_value("app", "icon.adaptive_background.filename", __import__("os").environ.get("GD3_ICON_BG", ""), raise_warning=False)\n        self.set_value("app", "presplash.filename", __import__("os").environ.get("GD3_PRESPLASH", ""), raise_warning=False)\n        self.set_value("app", "android.presplash_color", __import__("os").environ.get("GD3_PRESPLASH_COLOR", ""), raise_warning=False)\n        self.set_value("app", "android.add_resources", __import__("os").environ.get("GD3_RES", ""), raise_warning=False)|' "$DEPLOY_BZ" \
    && grep -q 'GD3_ICON_FG' "$DEPLOY_BZ" && grep -q 'GD3_PRESPLASH_COLOR' "$DEPLOY_BZ" && echo "[patch] GD3 adaptive icon + presplash 注入 OK" \
    && sed -i 's|"title", pysidedeploy_config.title)|"title", __import__("os").environ.get("GD3_APP_TITLE", "") or pysidedeploy_config.title)|' "$DEPLOY_BZ" \
    && sed -i 's|"package.name", pysidedeploy_config.title)|"package.name", __import__("os").environ.get("GD3_PKG_NAME", "") or pysidedeploy_config.title)|' "$DEPLOY_BZ" \
    && sed -i 's|f"org.{pysidedeploy_config.title}")|(__import__("os").environ.get("GD3_PKG_DOMAIN", "") or f"org.{pysidedeploy_config.title}"))|' "$DEPLOY_BZ" \
    && grep -q 'GD3_APP_TITLE' "$DEPLOY_BZ" && grep -q 'GD3_PKG_NAME' "$DEPLOY_BZ" && grep -q 'GD3_PKG_DOMAIN' "$DEPLOY_BZ" && echo "[patch] GD3 包名/显示名注入 OK"

# 非 root 构建用户(uid 1000 对齐 host): buildozer 在 root 下跑会崩(NoSectionError), 不能用 WARN_ON_ROOT 绕。
# chown 缓存目录(空卷首挂复制镜像属主)+ /opt/p4a(p4a cwd 末步 cp APK, root 属主下写不进致非零退出)。
# 不预建 android-sdk/licenses(否则 buildozer 误判已装、新 runner sdkmanager 缺失即崩), 让其自下 + accept_sdk_license。
# gradle init.gradle 仅国内构建用(GD3_GRADLE_CN=1 传); CI 直连 google()。
ARG GD3_GRADLE_CN=0
RUN useradd -m -u 1000 builder \
    && mkdir -p /home/builder/.pyside6_android_deploy /home/builder/.buildozer /home/builder/.gradle /home/builder/stage \
    && if [ "$GD3_GRADLE_CN" = "1" ]; then cp /opt/gradle-init.gradle /home/builder/.gradle/init.gradle; fi \
    && chown -R builder:builder /home/builder \
    && chown builder:builder /opt/p4a
# 状态栏沉浸(L1): Activity 主题补 statusBarColor=app 背景(@color/gd3_splash_bg 随明暗)+ windowLightStatusBar
# 图标翻转(@bool/gd3_light_status_bar, values/ 默认 true、GD3_RES 注入的 values-night false 覆盖)。
# 改镜像 /opt/p4a 模板(p4a 组 dist 重拷, 改卷副本会被覆盖); 单列末层只重建廉价离线层。
RUN QTSTR=/opt/p4a/pythonforandroid/bootstraps/qt/build/templates/strings.tmpl.xml \
    && sed -i '/<item name="android:windowSplashScreenBackground">@color\/gd3_splash_bg<\/item>/a\        <item name="android:windowDrawsSystemBarBackgrounds">true</item>\n        <item name="android:statusBarColor">@color/gd3_splash_bg</item>\n        <item name="android:windowLightStatusBar">@bool/gd3_light_status_bar</item>' "$QTSTR" \
    && sed -i '/<color name="gd3_splash_bg">#f3f3f3<\/color>/a\    <bool name="gd3_light_status_bar">true</bool>' "$QTSTR" \
    && grep -q 'statusBarColor' "$QTSTR" \
    && chown builder:builder "$QTSTR" \
    && echo "[patch] qt 状态栏沉浸 statusBarColor+windowLightStatusBar OK"

# APK 版本号经 GD3_VERSION 注入（buildozer 默认 0.1）+ 自动接受 SDK 协议（全新 runner 自下 SDK 时无人值守）。
# 单列末层，理由同上：改这里不触发重下。
RUN DEPLOY_BZ=/usr/local/lib/python3.11/site-packages/PySide6/scripts/deploy_lib/android/buildozer.py \
    && sed -i '/self.set_value("app", "title",/a\        self.set_value("app", "version", __import__("os").environ.get("GD3_VERSION", "") or "0.1")\n        self.set_value("app", "android.accept_sdk_license", "True")\n        self.set_value("buildozer", "log_level", "1")' "$DEPLOY_BZ" \
    && grep -q 'GD3_VERSION' "$DEPLOY_BZ" && grep -q 'accept_sdk_license' "$DEPLOY_BZ" && grep -q 'log_level' "$DEPLOY_BZ" && echo "[patch] GD3_VERSION + accept_sdk_license + log_level=1 注入 OK"

USER builder
WORKDIR /work
