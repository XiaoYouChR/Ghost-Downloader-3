package com.xychr.ghostdownloader.ui.components.task

import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.model.*

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
class TaskViewModel : ViewModel() {
    val categories = engineRepository.observe<CategoryState>("categoryState")
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), CategoryState())

    /**
     * 不保证引用稳定：进度每秒推一次，每次都产出新列表和新的运行中 TaskUiState 实例。
     * 下游拿 tasks 做 remember 只能挡住交互类重组（勾选、展开），挡不住进度 tick。
     */
    val state: StateFlow<TaskListState> = engineRepository.observe<List<TaskUiState>>("tasks")
        .combine(engineRepository.observe<Map<String, TaskSnapshot>>("taskProgress")) { tasks, progress ->
            TaskListState(tasks.map { task ->
                progress[task.id]?.let { p ->
                    task.copy(progress = p.progress, speed = p.speed, received = p.received)
                } ?: task
            }, TaskReadState.READY)
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), TaskListState())

    fun pause(taskId: String) = request("pause", taskId)

    fun stop(taskId: String) = request("stopTask", taskId)

    fun resume(taskId: String) {
        request("resume", taskId)
    }

    fun remove(taskId: String, shouldDeleteFiles: Boolean) =
        request("remove", taskId, shouldDeleteFiles)

    fun moveToFront(taskId: String) = request("moveToFront", taskId)

    fun redownload(taskId: String) {
        request("redownload", taskId)
    }

    /**
     * scopeIds 是作用域而非目标——目标由这里按最新快照算，调用方不要自己筛。
     * 作用域里没被选中的任务计入 skipped，让调用方能如实报告。
     */
    suspend fun requestBatch(action: TaskBatchAction, scopeIds: List<String>): TaskBatchResult {
        val snapshot = state.value
        if (snapshot.readState != TaskReadState.READY) return TaskBatchResult(0, 0, scopeIds.size)
        val targets = buildTaskBatchTargets(snapshot.tasks.filter { it.id in scopeIds })
        val ids = if (action == TaskBatchAction.START) targets.startIds else targets.pauseIds
        var submitted = 0
        var failed = 0
        for (id in ids) {
            try {
                engineRepository.invoke(if (action == TaskBatchAction.START) "resume" else "pause", id)
                submitted++
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                failed++
            }
        }
        return TaskBatchResult(submitted, failed, scopeIds.size - ids.size)
    }

    fun removeEach(taskIds: List<String>, shouldDeleteFiles: Boolean) =
        taskIds.forEach { request("remove", it, shouldDeleteFiles) }

    fun moveToFrontEach(taskIds: List<String>) = taskIds.forEach { request("moveToFront", it) }

    fun redownloadEach(taskIds: List<String>) {
        taskIds.forEach { request("redownload", it) }
    }

    suspend fun setCategory(taskIds: List<String>, categoryId: String) {
        engineRepository.invoke("setTaskCategory", engineRepository.encode(taskIds), categoryId)
    }

    private fun request(name: String, vararg args: Any?) {
        viewModelScope.launch { engineRepository.invoke(name, *args) }
    }
}
