package com.xychr.ghostdownloader.ui.components.task

import com.xychr.ghostdownloader.bridge.bridge
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
    val categories = bridge.observe<CategoryState>("categoryState")
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), CategoryState())

    val state: StateFlow<TaskListState> = bridge.observe<List<TaskUiState>>("tasks")
        .combine(bridge.observe<Map<String, TaskUiState>>("taskProgress")) { tasks, activeTasks ->
            TaskListState(tasks.map { it.update(activeTasks) }, true)
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), TaskListState())

    fun pause(taskId: String) = request("pause", taskId)

    fun stop(taskId: String) = request("stopTask", taskId)

    fun startSeeding(taskId: String) = request("startSeeding", taskId)

    fun stopSeeding(taskId: String) = request("stopSeeding", taskId)

    fun resume(taskId: String) {
        request("resume", taskId)
    }

    fun moveToFront(taskIds: List<String>) = request("moveToFront", bridge.encode(taskIds))

    fun startAll() = request("resumeAll")

    fun resumeEach(taskIds: List<String>) = taskIds.forEach { request("resume", it) }

    suspend fun pauseEach(taskIds: List<String>) {
        for (id in taskIds) {
            try {
                bridge.invoke("pause", id)
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) { }
        }
    }

    fun removeEach(taskIds: List<String>, shouldDeleteFiles: Boolean) =
        taskIds.forEach { request("remove", it, shouldDeleteFiles) }

    fun redownloadEach(taskIds: List<String>) {
        taskIds.forEach { request("redownload", it) }
    }

    suspend fun setCategory(taskIds: List<String>, categoryId: String) {
        bridge.invoke("setTaskCategory", bridge.encode(taskIds), categoryId)
    }

    private fun request(name: String, vararg args: Any?) {
        viewModelScope.launch { bridge.invoke(name, *args) }
    }
}
