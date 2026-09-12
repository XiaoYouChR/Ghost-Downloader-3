package com.xychr.ghostdownloader

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.packs.PackRegistry
import com.xychr.ghostdownloader.service.CHANNEL_PAIR
import com.xychr.ghostdownloader.service.CHANNEL_RUNNING
import com.xychr.ghostdownloader.service.KeepAlive
import com.xychr.ghostdownloader.service.startKeepAlive
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.distinctUntilChangedBy
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch

class App : Application() {

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    override fun onCreate() {
        super.onCreate()

        getSystemService(NotificationManager::class.java).apply {
            createNotificationChannel(NotificationChannel(CHANNEL_RUNNING, getString(R.string.notification_channel_running), NotificationManager.IMPORTANCE_LOW))
            createNotificationChannel(NotificationChannel(CHANNEL_PAIR, getString(R.string.notification_channel_pair), NotificationManager.IMPORTANCE_HIGH))
        }

        Python.start(AndroidPlatform(this))
        val module = Python.getInstance().getModule("engine")
        val packUiJson = module.callAttr("start").toString()
        PackRegistry.load(packUiJson)
        EngineRepository.bind(module.get("_engine")!!)

        scope.launch {
            EngineRepository.observe<KeepAlive>("keepAlive")
                .distinctUntilChangedBy { it.reason.isNotEmpty() }
                .filter { it.reason.isNotEmpty() }
                .collect { startKeepAlive(this@App) }
        }
    }
}
