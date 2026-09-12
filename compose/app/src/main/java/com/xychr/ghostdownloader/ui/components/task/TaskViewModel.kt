package com.xychr.ghostdownloader.ui.components.task

import com.xychr.ghostdownloader.engine.EngineRepository
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
    val categories = EngineRepository.observe<CategoryState>("categoryState")
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), CategoryState())

    val state: StateFlow<TaskListState> = EngineRepository.observe<List<TaskUiState>>("tasks")
        .combine(EngineRepository.observe<Map<String, TaskSnapshot>>("taskProgress")) { tasks, progress ->
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

    suspend fun requestBatch(action: TaskBatchAction, taskIds: List<String>): TaskBatchResult {
        val snapshot = state.value
        if (snapshot.readState != TaskReadState.READY) return TaskBatchResult(0, 0, taskIds.size)
        val targets = buildTaskBatchTargets(snapshot.tasks.filter { it.id in taskIds })
        val ids = if (action == TaskBatchAction.START) targets.startIds else targets.pauseIds
        var submitted = 0
        var failed = 0
        for (id in ids) {
            try {
                EngineRepository.invoke(if (action == TaskBatchAction.START) "resume" else "pause", id)
                submitted++
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                failed++
            }
        }
        return TaskBatchResult(submitted, failed, taskIds.size - ids.size)
    }

    fun removeEach(taskIds: List<String>, shouldDeleteFiles: Boolean) =
        taskIds.forEach { request("remove", it, shouldDeleteFiles) }

    fun moveToFrontEach(taskIds: List<String>) = taskIds.forEach { request("moveToFront", it) }

    fun redownloadEach(taskIds: List<String>) {
        taskIds.forEach { request("redownload", it) }
    }

    private fun request(name: String, vararg args: Any?) {
        viewModelScope.launch { EngineRepository.invoke(name, *args) }
    }
}
