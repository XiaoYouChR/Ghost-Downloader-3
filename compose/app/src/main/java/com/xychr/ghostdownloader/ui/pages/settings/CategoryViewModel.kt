package com.xychr.ghostdownloader.ui.pages.settings

import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.Category
import com.xychr.ghostdownloader.model.CategoryState
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class CategoryViewModel : ViewModel() {

    val state: StateFlow<CategoryState?> =
        EngineRepository.observe<CategoryState>("categoryState")
            .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    private val _isSaving = MutableStateFlow(false)
    val isSaving = _isSaving.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error = _error.asStateFlow()

    fun setEnabled(isEnabled: Boolean) = write {
        EngineRepository.invoke("setSetting", "isCategoryEnabled", isEnabled)
    }

    suspend fun add(category: Category) {
        EngineRepository.invoke("addCategory", EngineRepository.encode(category))
    }

    suspend fun update(category: Category) {
        EngineRepository.invoke("updateCategory", EngineRepository.encode(category))
    }

    fun remove(categoryId: String) = write {
        EngineRepository.invoke("removeCategory", categoryId)
    }

    fun reset() = write {
        EngineRepository.invoke("resetCategories")
    }

    fun setOrder(ids: List<String>) = write {
        EngineRepository.invoke("reorderCategories", EngineRepository.encode(ids))
    }

    private fun write(block: suspend () -> Unit) {
        if (_isSaving.value) return
        _isSaving.value = true
        viewModelScope.launch {
            try {
                block()
                _error.value = null
            } catch (e: CancellationException) { throw e }
            catch (failure: Exception) { _error.value = failure.message }
            finally { _isSaving.value = false }
        }
    }
}
