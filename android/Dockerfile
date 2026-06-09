# Ghost Downloader 3 —— Android 构建工具链镜像
#
# 设计目标：本地 == CI。WSL 本地和 GitHub Actions 跑同一个镜像，消除环境漂移。
# 容器只负责构建 APK；adb 装机/测试在 host 进行（host 已连真机）。
#
# 镜像源参数化：默认走官方源（CI/海外直连），本地（GFW 后）通过 build-arg 传国内镜像，
# 同一份 Dockerfile 两种网络环境通用。run_build.sh 检测到国内环境会自动传镜像参数。
#
# 关键约束：
#   - Qt 的 Android wheel 是 cp311 专用（非 abi3），所以 host Python 必须 3.11 -> python:3.11 基础镜像
#   - pyside6-android-deploy 内置 NDK r27c，会自动下载到 ~/.pyside6_android_deploy（用挂载卷缓存）
#   - Rust target aarch64-linux-android 为后续 qh3/jh2/zstandard 的 p4a recipe 预备（S4）
#   - buildozer==1.5.0 / cython==0.29.33 是 PySide6 deploy 默认锁定版本
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

# --- 对 pyside6-android-deploy 的 patch 集合 ---
# 1) 钉死 Python 3.11.15：Qt wheel 是 cp311，但 p4a develop 的 python3 recipe 默认拉 3.14，
#    会装出 libpython3.14 与 cp311 不匹配（博客同款修法）。
# 2) requirements/permissions 环境变量可注入：deploy 写死这两项，改为可经 GD3_EXTRA_REQ /
#    GD3_EXTRA_PERM 追加（如 pyjnius、MANAGE_EXTERNAL_STORAGE），镜像保持通用、CI 同样传参。
# 3) include_exts 加 toml：否则 manifest.toml 不进 APK。
# 4) 增量构建：deploy 默认每次删/move /work/.buildozer 导致全量重编 CPython，改为保留原地，
#    让 buildozer 增量复用已编 dist（CI 全新无 .buildozer，无副作用）。
# 5) Qt 模块经 GD3_QT_MODULES 环境变量注入：deploy 默认扫源码自动探测 + 依赖闭包，会扫到 app
#    桌面分支的 PySide6.QtDBus 而 Android Qt wheel 无 libQt6DBus -> 崩；且扫不到 qfluentwidgets
#    (打包依赖非 project 源)运行时要的 Xml/SvgWidgets/Core5Compat。spec 里写 [qt]modules 无效
#    （Config.__init__ 末尾 `self.modules = []` 会抹空），故必须 env 注入，非空即跳过扫描直接用此清单。
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
# 增量：保留 /work/.buildozer 复用已编 CPython/recipe。

# --- 烘焙 Qt 的 aarch64 Android wheel（避免每次构建重新下载 ~200MB）---
RUN mkdir -p /opt/qt-android-wheels && cd /opt/qt-android-wheels \
    && wget -q "${QT_DL}/pyside6/PySide6-6.10.2-6.10.2-cp311-cp311-android_aarch64.whl" \
    && wget -q "${QT_DL}/shiboken6/shiboken6-6.10.2-6.10.2-cp311-cp311-android_aarch64.whl" \
    && ls -la /opt/qt-android-wheels

# --- 本地 p4a + 修复 pyjnius 在 qt bootstrap 下缺 WebView_AndroidGetJNIEnv ---
# pyjnius(genericndkbuild 变体) 把 JNIEnv getter 指向 WebView_AndroidGetJNIEnv，该符号由
# webview/service_only bootstrap 的 pyjniusjni.c 提供；qt bootstrap 的 Android.mk 只编 start.c，
# 故 libmain 缺符号 -> jnius.so dlopen 失败。克隆 p4a develop 到 /opt/p4a，给 qt bootstrap 的
# libmain 补编 pyjniusjni.c。deploy 经 GD3_P4A_SOURCE 用这个本地 p4a（覆盖 buildozer 默认 clone）。
ARG P4A_GIT_URL=https://github.com/kivy/python-for-android.git
ENV GD3_P4A_SOURCE=/opt/p4a
COPY patches/qt_pyjniusjni.c /opt/qt_pyjniusjni.c
COPY gradle-init.gradle /opt/gradle-init.gradle
# 自定义 p4a recipe（HTTP 栈交叉编译）：jh2(maturin/pyo3) 等。塞进 p4a 的 recipes/ 成为内置
# recipe，requirements 出现 jh2 时 p4a 自动用 RustCompiledComponentsRecipe 交叉编译，而非
# --only-binary 忽略。qh3 不放（v1 缓做，避开 aws-lc android 交叉编译）。
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

# --- 预置 bionic arm64 ffmpeg/ffprobe（hzw1199 8.1.1，NDK r28c/Android28+/LGPL/16KB）---
# 改名 lib*.so 供 gd3ffmpeg recipe install_libs，走 jniLibs->nativeLibraryDir->exec 通道。
# image build 的 RUN 无 host 代理：CI 走 raw.githubusercontent 直连，本地经 jsDelivr CDN
# （run_build.sh 检测 GD3_CN_MIRROR=1 时传 FFMPEG_BASE=jsDelivr）。
ARG FFMPEG_BASE=https://raw.githubusercontent.com/hzw1199/Android-FFmpeg-Prebuilt/main/ffmpeg-8.1.1/bin
# N_m3u8DL-RE android-bionic-arm64（.NET AOT 单体二进制，m3u8 下载器）。CI 直连 github release，
# china 走 ghfast.top 镜像（run_build.sh 的 GD3_CN_MIRROR=1 传）。
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

# --- app 启动器图标 + adaptive icon + presplash + 包名/显示名：让 deploy 优先读 GD3_* 环境变量 ---
# 单独成层且置于昂贵下载层(qt wheel/p4a/ffmpeg)之后, 改它只重建廉价的 user-setup 层。
# 图标: deploy 默认 PySide6 自带 python logo; 注入后 icon.filename 指向我们的 logo.png。
# adaptive icon + presplash: deploy 只写 icon.filename(传统方图, API26+ 启动器填白角致桌面白边),
#   也不配 presplash(留默认 Kivy "Loading..." 黑底图)。这里追加四键各读独立环境变量:
#   icon.adaptive_foreground/background.filename(消白边) + presplash.filename/presplash_color(冷启动图)。
# 包名/显示名: deploy 默认 title=package.name=--name、package.domain=org.{title} → 派生丑名
#   org.x.x, 且 title 带空格会让 package.name 非法。三字段解耦各读独立环境变量:
#   GD3_APP_TITLE(显示名, 可带空格) / GD3_PKG_NAME(无空格合法) / GD3_PKG_DOMAIN(反向域名)。
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

# --- 非 root 构建用户（uid 1000 对齐 host，避免 buildozer 的 root 警告阻塞 + 挂载目录可写）---
# 不可用 BUILDOZER_WARN_ON_ROOT 绕过——它会在 `buildozer init`（空配置）阶段触发
# configparser.NoSectionError 崩溃，须以非 root 用户跑(euid≠0)。
# 预建缓存目录并 chown：空命名卷首次挂载从镜像同名目录复制属主，避免 root 属主致 builder 写不进。
# 预置 Android SDK license 哈希：buildozer 自管 SDK 装 build-tools 须接受 license，非交互下默认拒绝
# -> 缺 aidl 构建失败；预置后 sdkmanager 视为已接受。
# gradle init.gradle 仅 china 构建用（Aliyun 优先）；CI(US runner) 不写它直连 google()，避免 Aliyun
# 从海外慢/卡。run_build.sh 的 GD3_CN_MIRROR=1 传 GD3_GRADLE_CN=1。
ARG GD3_GRADLE_CN=0
RUN useradd -m -u 1000 builder \
    && mkdir -p /home/builder/.pyside6_android_deploy /home/builder/.buildozer /home/builder/.gradle /home/builder/stage \
    && if [ "$GD3_GRADLE_CN" = "1" ]; then cp /opt/gradle-init.gradle /home/builder/.gradle/init.gradle; fi \
    && chown -R builder:builder /home/builder \
    && chown builder:builder /opt/p4a
# 不预建 android-sdk/licenses：那会让 buildozer 误判 SDK 已装(_install_android_sdk 只判目录是否存在)、
# 跳过下载 cmdline-tools，全新 runner 上 tools/bin/sdkmanager 缺失即崩。改为让 buildozer 自下 SDK +
# accept_sdk_license=True(下方 deploy 补丁注入)无人值守接受协议。本地卷已装满 SDK 不受影响。
# /opt/p4a 顶层 chown 给 builder：p4a 用本地 source_dir 时 cwd=/opt/p4a，其 _finish_package
# 末步在 cwd cp 出带版本号的 APK 副本。root 属主下 builder 写不进 -> "cp: Permission denied"
# 让 buildozer 整体退非零，chown 后干净退 0。
# 状态栏沉浸(L1)：给 Activity 主题补 statusBarColor + windowLightStatusBar — 底色=app 背景
# (@color/gd3_splash_bg 随系统明暗)，图标亮暗经 @bool/gd3_light_status_bar 翻转(values/ 默认 true
# + GD3_RES 注入的 values-night false 覆盖)。必须改镜像 /opt/p4a 模板 —— p4a 组 dist 时从这里重拷，
# 改卷里副本会被覆盖。单列成末层(在所有联网下载层之后)，改这里只重建廉价离线层不触发重下。
RUN QTSTR=/opt/p4a/pythonforandroid/bootstraps/qt/build/templates/strings.tmpl.xml \
    && sed -i '/<item name="android:windowSplashScreenBackground">@color\/gd3_splash_bg<\/item>/a\        <item name="android:windowDrawsSystemBarBackgrounds">true</item>\n        <item name="android:statusBarColor">@color/gd3_splash_bg</item>\n        <item name="android:windowLightStatusBar">@bool/gd3_light_status_bar</item>' "$QTSTR" \
    && sed -i '/<color name="gd3_splash_bg">#f3f3f3<\/color>/a\    <bool name="gd3_light_status_bar">true</bool>' "$QTSTR" \
    && grep -q 'statusBarColor' "$QTSTR" \
    && chown builder:builder "$QTSTR" \
    && echo "[patch] qt 状态栏沉浸 statusBarColor+windowLightStatusBar OK"

# APK 版本号经 GD3_VERSION 注入（buildozer 默认 0.1）+ 自动接受 SDK 协议（全新 runner 自下 SDK 时无人值守）。
# 单列末层，理由同上：改这里不触发重下。
RUN DEPLOY_BZ=/usr/local/lib/python3.11/site-packages/PySide6/scripts/deploy_lib/android/buildozer.py \
    && sed -i '/self.set_value("app", "title",/a\        self.set_value("app", "version", __import__("os").environ.get("GD3_VERSION", "") or "0.1")\n        self.set_value("app", "android.accept_sdk_license", "True")' "$DEPLOY_BZ" \
    && grep -q 'GD3_VERSION' "$DEPLOY_BZ" && grep -q 'accept_sdk_license' "$DEPLOY_BZ" && echo "[patch] GD3_VERSION + accept_sdk_license 注入 OK"

USER builder
WORKDIR /work
