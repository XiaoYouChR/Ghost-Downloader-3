package com.xychr.ghostdownloader.ui.components.task

import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateListOf

@Stable
class SelectionState {
    var isActive by mutableStateOf(false)
        private set

    private val _selectedIds = mutableStateListOf<String>()
    val selectedIds: List<String> get() = _selectedIds
    val count get() = _selectedIds.size

    fun start() { isActive = true }

    fun update(taskIds: List<String>) {
        val hadSelection = _selectedIds.isNotEmpty()
        _selectedIds.removeAll { it !in taskIds }
        if (hadSelection && _selectedIds.isEmpty()) exit()
    }

    fun enter(taskId: String) {
        isActive = true
        _selectedIds.add(taskId)
    }

    fun toggle(taskId: String) {
        if (taskId in _selectedIds) _selectedIds.remove(taskId)
        else _selectedIds.add(taskId)
        if (_selectedIds.isEmpty()) exit()
    }

    fun selectAll(visibleIds: List<String>) {
        _selectedIds.clear()
        _selectedIds.addAll(visibleIds)
    }

    fun invert(visibleIds: List<String>) {
        val current = _selectedIds.toSet()
        _selectedIds.clear()
        _selectedIds.addAll(visibleIds.filter { it !in current })
        if (_selectedIds.isEmpty()) exit()
    }

    fun exit() {
        isActive = false
        _selectedIds.clear()
    }
}
