plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    id("com.chaquo.python")
    kotlin("plugin.serialization") version libs.versions.kotlin.get()
}

android {
    namespace = "io.github.xiaoyouchr.ghostdownloader"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "io.github.xiaoyouchr.ghostdownloader"
        minSdk = 28
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }
    buildFeatures {
        compose = true
    }
    androidResources {
        generateLocaleConfig = true
    }
    sourceSets {
        getByName("main") {
            // AGP 9 不收 Provider，用字面路径；任务依赖在下面 configureEach 里接
            assets.srcDir("$projectDir/build/extension-assets")
        }
    }
}

// 浏览器扩展的 CRX 和桌面共用一份，别在 compose 下再放一个副本
val syncExtensionAsset = tasks.register<Sync>("syncExtensionAsset") {
    from("../../app/assets/chrome_extension.crx")
    into(layout.buildDirectory.dir("extension-assets"))
}

val syncEngineSource = tasks.register<Sync>("syncEngineSource") {
    from("../../app") {
        include("**/*.py")
        exclude("view/**")
        exclude("startup.py")
        exclude("signal_bus.py")
        exclude("config/cfg.py")
        exclude("config/paths.py")
        exclude("platform/application.py")
        exclude("platform/desktop.py")
        exclude("platform/desktop_keepalive.py")
        exclude("platform/desktop_notification.py")
        exclude("platform/file_association.py")
        exclude("platform/hidden_subprocess.py")
        exclude("platform/run_at_login.py")
        exclude("platform/url_scheme.py")
        exclude("platform/windows.py")
    }
    into(layout.buildDirectory.dir("python-engine/app"))
}

// View 文件不进 APK——Android 侧的卡片和设置界面是 Compose 写的
val androidPacks = listOf(
    "http_pack", "ftp_pack", "github_pack", "huggingface_pack", "bittorrent_pack",
    "ed2k_pack", "ffmpeg_pack", "m3u8_pack", "yt_dlp_pack", "bili_pack",
)

val syncFeatureSource = tasks.register<Sync>("syncFeatureSource") {
    androidPacks.forEach { pack ->
        from("../../features/$pack") {
            include("**/*.py", "manifest.toml")
            exclude("cards.py", "setting_cards.py")
            exclude("web_tracker/card.py", "web_tracker/dialog.py")
            into(pack)
        }
    }
    into(layout.buildDirectory.dir("python-engine/features"))
    doLast {
        layout.buildDirectory.file("python-engine/features/__init__.py").get().asFile.apply {
            parentFile.mkdirs()
            writeText("")
        }
    }
}

tasks.configureEach {
    if (name.contains("Python") && name.contains("merge", ignoreCase = true)) {
        dependsOn(syncEngineSource, syncFeatureSource)
    }
    if (name.startsWith("merge") && name.endsWith("Assets")) {
        dependsOn(syncExtensionAsset)
    }
}

chaquopy {
    defaultConfig {
        version = "3.14"
        buildPython(System.getenv("BUILD_PYTHON") ?: "python3.14")
        extractPackages("features")
        pip {
            install("${projectDir}/../build-scripts/dist/wreq-0.12.1-cp314-abi3-android_24_arm64_v8a.whl")
            install("${projectDir}/../build-scripts/dist/libtorrent-2.1.1-cp314-cp314-android_24_arm64_v8a.whl")
            install("loguru")

            install("aioftp")
            install("m3u8")
            install("mpegdash")
            install("websockets")
        }
    }
    sourceSets {
        getByName("main") {
            srcDir("src/main/python")
            srcDir(layout.buildDirectory.dir("python-engine"))
        }
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material3.adaptive.navigation.suite)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.zxing.core)
    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
