package com.xychr.ghostdownloader

import android.app.Application
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.xychr.ghostdownloader.engine.EngineFlows
import com.xychr.ghostdownloader.engine.SettingRanges
import com.xychr.ghostdownloader.engine.createEngineRepository
import com.xychr.ghostdownloader.engine.engineRepository
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

class App : Application() {

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    val notices by lazy { Notices(this) }

    override fun onCreate() {
        super.onCreate()

        val flows = EngineFlows()

        Python.start(AndroidPlatform(this))
        val module = Python.getInstance().getModule("engine")
        val packUiJson = module.callAttr("start", flows).toString()
        PackRegistry.load(packUiJson)
        val engine = module.get("_engine")!!
        SettingRanges.load(engine.callAttr("settingRanges").toString())
        createEngineRepository(engine, flows)

        notices.start()

        ProcessLifecycleOwner.get().lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onStop(owner: LifecycleOwner) {
                scope.launch(Dispatchers.IO) { engineRepository.invoke("flush") }
            }
        })

        scope.launch {
            engineRepository.observe<KeepAlive>("keepAlive")
                .distinctUntilChangedBy { it.reason.isNotEmpty() }
                .filter { it.reason.isNotEmpty() }
                .collect { startKeepAlive(this@App) }
        }
    }
}
