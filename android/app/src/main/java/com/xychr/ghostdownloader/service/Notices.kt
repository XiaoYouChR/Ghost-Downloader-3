package com.xychr.ghostdownloader.service

import android.app.Application
import android.content.Context
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ProcessLifecycleOwner
import com.xychr.ghostdownloader.engine.engineRepository
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

class Notices(app: Application) {

    private val context: Context = buildLocalizedContext(app)
    private val scope = CoroutineScope(Dispatchers.Main.immediate + SupervisorJob())
    private val notices = MutableSharedFlow<Notice>(extraBufferCapacity = 8)
    private var completedInBackground = 0

    val inApp: SharedFlow<Notice> = notices.asSharedFlow()

    fun start() {
        context.createNoticeChannels()
        scope.launch {
            engineRepository.observeEvent<Notice>("notice").collect { show(it, isForeground()) }
        }
        scope.launch {
            engineRepository.observe<PairRequest?>("pairRequest").collect { pair ->
                context.sendPair(pair.takeIf { !isForeground() })
            }
        }
    }

    private suspend fun show(notice: Notice, isForeground: Boolean) {
        if (isForeground) completedInBackground = 0
        when (notice) {
            is Notice.TaskCompleted -> if (!isForeground) {
                completedInBackground++
                context.sendCompleted(notice, completedInBackground)
            }

            is Notice.TaskFailed,
            is Notice.DiskSpace,
            is Notice.DraftTaken -> if (isForeground) notices.emit(notice) else context.send(notice)

            is Notice.ExtensionUpdated -> if (isForeground) notices.emit(notice)
        }
    }

    private fun isForeground() =
        ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)
}
