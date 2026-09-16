package com.xychr.ghostdownloader.ui.pages.settings

import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.model.Category
import com.xychr.ghostdownloader.model.CategoryState
import com.xychr.ghostdownloader.model.TaskUiState
import com.xychr.ghostdownloader.model.TaskError
import com.xychr.ghostdownloader.i18n.toTaskError
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class CategoryViewModel : ViewModel() {

    val state: StateFlow<CategoryState?> =
        engineRepository.observe<CategoryState>("categoryState")
            .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    /** 每个分类下的任务数，用于告诉用户删除会波及多少任务。 */
    val taskCounts: StateFlow<Map<String, Int>> =
        engineRepository.observe<List<TaskUiState>>("tasks")
            .map { tasks -> tasks.groupingBy { it.categoryId }.eachCount() }
            .stateIn(viewModelScope, SharingStarted.Eagerly, emptyMap())

    private val _isSaving = MutableStateFlow(false)
    val isSaving = _isSaving.asStateFlow()

    private val _error = MutableStateFlow<TaskError?>(null)
    val error = _error.asStateFlow()

    fun setEnabled(isEnabled: Boolean) = write {
        engineRepository.invoke("setSetting", "isCategoryEnabled", isEnabled)
    }

    suspend fun add(category: Category) {
        engineRepository.invoke("addCategory", engineRepository.encode(category))
    }

    suspend fun update(category: Category) {
        engineRepository.invoke("updateCategory", engineRepository.encode(category))
    }

    fun remove(categoryId: String) = write {
        engineRepository.invoke("removeCategory", categoryId)
    }

    fun reset() = write {
        engineRepository.invoke("resetCategories")
    }

    fun setOrder(ids: List<String>) = write {
        engineRepository.invoke("reorderCategories", engineRepository.encode(ids))
    }

    private fun write(block: suspend () -> Unit) {
        if (_isSaving.value) return
        _isSaving.value = true
        viewModelScope.launch {
            try {
                block()
                _error.value = null
            } catch (e: CancellationException) { throw e }
            catch (failure: Exception) { _error.value = failure.toTaskError() }
            finally { _isSaving.value = false }
        }
    }
}
