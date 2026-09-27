package com.xychr.ghostdownloader

import android.app.Application
import android.system.Os
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.xychr.ghostdownloader.bridge.BridgeFlows
import com.xychr.ghostdownloader.bridge.SettingRanges
import com.xychr.ghostdownloader.bridge.createBridge
import com.xychr.ghostdownloader.bridge.bridge
import com.xychr.ghostdownloader.packs.PackRegistry
import com.xychr.ghostdownloader.service.KeepAlive
import com.xychr.ghostdownloader.service.Notices
import com.xychr.ghostdownloader.service.startKeepAlive
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.distinctUntilChangedBy
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch
import java.io.File

class App : Application() {

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    val notices by lazy { Notices(this) }

    override fun onCreate() {
        super.onCreate()
        setupNativeLibraryPath()

        val flows = BridgeFlows()

        Python.start(AndroidPlatform(this))
        val module = Python.getInstance().getModule("bridge")
        val packUiJson = module.callAttr("start", flows).toString()
        PackRegistry.load(packUiJson)
        val python = module.get("_bridge")!!
        SettingRanges.load(python.callAttr("request", "settingRanges").toString())
        createBridge(python, flows)

        notices.start()

        ProcessLifecycleOwner.get().lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onStop(owner: LifecycleOwner) {
                scope.launch(Dispatchers.IO) { bridge.invoke("flush") }
            }
        })

        scope.launch {
            bridge.observe<KeepAlive>("keepAlive")
                .distinctUntilChangedBy { it.reason.isNotEmpty() }
                .filter { it.reason.isNotEmpty() }
                .collect { startKeepAlive(this@App) }
        }
    }

    // Android BoringSSL 缺少 .NET NativeAOT 依赖的 ASN1 符号，
    // 外部二进制 dlopen("libssl.so") 会 SIGABRT
    private fun setupNativeLibraryPath() {
        val nativeDir = applicationInfo.nativeLibraryDir
        val shimDir = File(filesDir, "openssl_shim")
        shimDir.mkdirs()
        val target = File(nativeDir, "libssl_python.so")
        if (target.exists()) {
            val link = File(shimDir, "libssl.so")
            link.delete()
            Os.symlink(target.absolutePath, link.absolutePath)
        }
        Os.setenv("LD_LIBRARY_PATH", "${shimDir.absolutePath}:$nativeDir", true)
    }
}
