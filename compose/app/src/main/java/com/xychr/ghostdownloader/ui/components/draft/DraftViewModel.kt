package com.xychr.ghostdownloader.ui.components.draft
import com.xychr.ghostdownloader.model.*

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.xychr.ghostdownloader.i18n.toTaskError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import com.xychr.ghostdownloader.ui.util.isValidOutputFolder

data class DraftState(
    val urls: String = "",
    val items: List<DraftItem> = emptyList(),
    val isWorking: Boolean = false,
    val error: TaskError? = null,
    val globalFolder: String = "",
    val subworkerCount: Int = 0,
) {
    val isFolderValid: Boolean get() = isValidOutputFolder(globalFolder)

    val canConfirm: Boolean get() {
        val input = urls.lineSequence().map(String::trim).filter(String::isNotEmpty).distinct().toList()
        return !isWorking && isFolderValid && (items.any { it.error == null } || (input.isNotEmpty() && input != items.map { it.url }))
    }
}

data class DraftChange(val action: String, val arguments: List<Any?>)

class DraftViewModel(
    private val send: suspend (String, List<Any?>) -> Unit,
    draftFlow: Flow<DraftProjection>,
    categoriesFlow: Flow<CategoryState>,
) : ViewModel() {
    val categories: StateFlow<CategoryState> = categoriesFlow.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), CategoryState())
    private val mutableState = MutableStateFlow(DraftState())
    val state: StateFlow<DraftState> = mutableState.asStateFlow()
    private var inputJob: Job? = null
    private var parsedUrls = ""
    private var hasLoaded = false
    private var hasInitialFolder = false

    init { viewModelScope.launch { draftFlow.collect(::onDraft) } }

    private fun onDraft(projection: DraftProjection) {
        val current = state.value
        if (!hasLoaded && current.urls.isEmpty()) {
            parsedUrls = projection.items.joinToString("\n") { it.url }
            mutableState.value = current.copy(urls = parsedUrls)
        }
        hasLoaded = true
        var next = state.value.copy(items = projection.items)
        if (!hasInitialFolder && next.globalFolder.isEmpty()) {
            val engineFolder = projection.outputFolder.ifEmpty {
                projection.items.firstOrNull { it.error == null && !it.isParsing }?.outputFolder.orEmpty()
            }
            if (engineFolder.isNotEmpty()) {
                hasInitialFolder = true
                next = next.copy(globalFolder = engineFolder)
            }
        }
        if (next.subworkerCount == 0 && projection.subworkerCount > 0) {
            next = next.copy(subworkerCount = projection.subworkerCount)
        }
        mutableState.value = next
    }

    fun setUrls(urls: String) {
        if (state.value.isWorking) return
        mutableState.value = state.value.copy(urls = urls)
        inputJob?.cancel()
        inputJob = viewModelScope.launch { delay(1000); sendOptions(); parseInput() }
    }

    private suspend fun parseInput() {
        val urls = state.value.urls.trim()
        if (urls == parsedUrls) return
        send("parse", listOf(urls))
        parsedUrls = urls
    }

    private suspend fun sendOptions() {
        val current = state.value
        val folder = current.globalFolder.trim()
        if (folder.isNotEmpty() && current.isFolderValid) send("setDraftOutputFolder", listOf(folder))
        send("setDraftSubworkerCount", listOf(current.subworkerCount))
    }

    suspend fun setName(url: String, name: String) = sendDraft(url, "setName", listOf(name))

    fun setGlobalFolder(folder: String) { mutableState.value = state.value.copy(globalFolder = folder) }
    fun setSubworkerCount(count: Int) { mutableState.value = state.value.copy(subworkerCount = count) }

    suspend fun setCategory(url: String, choice: String?): Boolean = update(url, listOf(DraftChange("setCategory", listOf(choice))))

    fun updateFiles(url: String, initial: List<DraftFile>, edited: List<DraftFile>) {
        val changes = fileChanges(initial, edited)
        if (changes.isEmpty()) return
        viewModelScope.launch { update(url, changes) }
    }

    private suspend fun sendDraft(url: String, action: String, args: List<Any?>) {
        send("setDraft", listOf(url, action) + args)
    }

    private suspend fun update(url: String, changes: List<DraftChange>): Boolean = try {
        changes.forEach { sendDraft(url, it.action, it.arguments) }
        true
    } catch (error: CancellationException) { throw error }
    catch (error: Exception) { mutableState.value = state.value.copy(error = error.toTaskError()); false }

    suspend fun sendPack(url: String, action: String, args: List<Any?>) {
        if (action == "probe") send("probeDraft", listOf(url) + args)
        else sendDraft(url, action, args)
    }

    suspend fun confirm(autoStart: Boolean = true): Boolean = runWorking { inputJob?.cancel(); sendOptions(); parseInput(); send("confirmDraft", listOf(autoStart)); stop() }
    suspend fun cancel(): Boolean = runWorking { inputJob?.cancel(); send("clearDraft", emptyList()); stop() }

    private fun stop() { parsedUrls = ""; hasInitialFolder = false; mutableState.value = DraftState(isWorking = true) }

    private suspend fun runWorking(block: suspend () -> Unit): Boolean {
        if (state.value.isWorking) return false
        mutableState.value = state.value.copy(isWorking = true, error = null)
        return try {
            withContext(NonCancellable) { block() }
            true
        } catch (error: CancellationException) { throw error }
        catch (error: Exception) { mutableState.value = state.value.copy(error = error.toTaskError()); false }
        finally { mutableState.value = state.value.copy(isWorking = false) }
    }
}

fun fileChanges(initial: List<DraftFile>, edited: List<DraftFile>): List<DraftChange> = buildList {
    if (edited.map { it.index to it.isSelected } != initial.map { it.index to it.isSelected }) {
        add(DraftChange("setSelection", listOf(edited.filter { it.isSelected }.joinToString(",") { it.index.toString() })))
    }
    val initialByIndex = initial.associateBy { it.index }
    edited.forEach { file ->
        val path = initialByIndex[file.index]?.path
        if (path != null && file.path != path) add(DraftChange("setFileName", listOf(file.index, file.path.trim())))
    }
}
