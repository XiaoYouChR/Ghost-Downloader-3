package com.xychr.ghostdownloader.service

import android.app.Application
import android.content.Context
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ProcessLifecycleOwner
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.Notice
import com.xychr.ghostdownloader.model.PairRequest
import com.xychr.ghostdownloader.ui.platform.buildLocalizedContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch

/**
 * Notice 的分流处。前台走应用内提示，后台走系统通知，出口由种类决定——
 * 这张策略表只存在于 show() 的那个 when 里，不散落到各个发生点。
 */
class Notices(app: Application) {

    /** Service 不走 attachBaseContext，不本地化的话通知会用系统语言而不是用户选的语言。 */
    private val context: Context = buildLocalizedContext(app)
    private val scope = CoroutineScope(Dispatchers.Main.immediate + SupervisorJob())
    private val notices = MutableSharedFlow<Notice>(extraBufferCapacity = 8)

    val inApp: SharedFlow<Notice> = notices.asSharedFlow()

    fun start() {
        context.createNoticeChannels()
        scope.launch {
            EngineRepository.observe<Notice>("notice").collect { show(it, isForeground()) }
        }
        scope.launch {
            EngineRepository.observe<PairRequest?>("pairRequest").collect { context.sendPair(it) }
        }
    }

    private suspend fun show(notice: Notice, isForeground: Boolean) {
        when (notice) {
            // 前台时列表那一行已经是 COMPLETED 了，再弹一条是噪音
            is Notice.TaskCompleted -> if (!isForeground) context.send(notice)

            is Notice.TaskFailed,
            is Notice.DiskSpace,
            is Notice.DraftTaken -> if (isForeground) notices.emit(notice) else context.send(notice)

            // 纯 FYI，不值得在后台打扰
            is Notice.ExtensionUpdated -> if (isForeground) notices.emit(notice)
        }
    }

    private fun isForeground() =
        ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)
}
