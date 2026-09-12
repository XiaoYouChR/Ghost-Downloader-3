import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.chaquopy)
}

// 桌面的发布流水线也从 constants.py 读版本号
val engineVersion = file("../../app/config/constants.py").readLines()
    .first { it.startsWith("VERSION") }
    .substringAfter('"').substringBefore('"')

// 没有 keystore.properties 时 release 出未签名 APK
val signing = Properties().apply {
    rootProject.file("keystore.properties").takeIf(File::exists)?.inputStream()?.use(::load)
}

android {
    namespace = "com.xychr.ghostdownloader"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.xychr.ghostdownloader"
        minSdk = 28
        targetSdk = 37
        versionName = engineVersion
        versionCode = engineVersion.substringBefore('-').split('.')
            .map(String::toInt)
            .let { (major, minor, patch) -> major * 10000 + minor * 100 + patch }

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        create("release") {
            storeFile = signing.getProperty("storeFile")?.let(rootProject::file)
            storePassword = signing.getProperty("storePassword")
            keyAlias = signing.getProperty("keyAlias")
            keyPassword = signing.getProperty("keyPassword")
            // minSdk 28 用不上 v1；v3 带证书轮换，AGP 默认不开
            enableV1Signing = false
            enableV2Signing = true
            enableV3Signing = true
        }
    }

    buildTypes {
        release {
            optimization {
                enable = true
            }
            signingConfig = signingConfigs.getByName("release").takeIf { it.storeFile != null }
        }
        create("benchmark") {
            initWith(getByName("release"))
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += "release"
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
}

// CRX 和桌面共用一份，不放副本
abstract class SyncExtensionAsset : DefaultTask() {
    @get:InputFile
    abstract val crx: RegularFileProperty

    @get:OutputDirectory
    abstract val outputFolder: DirectoryProperty

    @TaskAction
    fun run() {
        val folder = outputFolder.get().asFile
        folder.mkdirs()
        crx.get().asFile.copyTo(folder.resolve("chrome_extension.crx"), overwrite = true)
    }
}

val syncExtensionAsset = tasks.register<SyncExtensionAsset>("syncExtensionAsset") {
    crx = layout.projectDirectory.file("../../app/assets/chrome_extension.crx")
}

// 变体 API 而非 sourceSets.assets.srcDir，后者不建立 task 依赖
androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(
            syncExtensionAsset,
            SyncExtensionAsset::outputFolder,
        )
    }
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
    implementation(libs.backdrop)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.zxing.core)
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
