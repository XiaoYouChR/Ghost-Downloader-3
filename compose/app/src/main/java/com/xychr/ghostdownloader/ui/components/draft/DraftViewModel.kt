package com.xychr.ghostdownloader.ui.components.draft
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.*

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class DraftState(
    val urls: String = "",
    val items: List<DraftItem> = emptyList(),
    val isWorking: Boolean = false,
    val error: String? = null,
    val probing: Set<String> = emptySet(),
    val probeErrors: Map<String, DraftProbeError> = emptyMap(),
) {
    val canConfirm: Boolean get() {
        val input = urls.lineSequence().map(String::trim).filter(String::isNotEmpty).distinct().toList()
        return !isWorking && (items.any { it.error == null } || (input.isNotEmpty() && input != items.map { it.url }))
    }
}

data class DraftProbeError(val kind: String, val message: String)

data class DraftChange(val action: String, val arguments: List<Any>)

data class DraftEdits(
    val name: String,
    val files: List<DraftFile>,
    val isVideoEnabled: Boolean,
    val isAudioEnabled: Boolean,
    val isCoverEnabled: Boolean,
    val videoTier: String,
    val audioTier: String,
    val subtitles: List<String>,
    val audioLanguages: List<String>,
    val start: Int,
    val end: Int,
    val categoryChoice: String? = null,
    val outputFolder: String = "",
)

class DraftViewModel(
    private val fetchItems: suspend () -> List<DraftItem>,
    private val send: suspend (String, List<Any>) -> Unit,
    categoriesFlow: Flow<CategoryState>,
) : ViewModel() {
    val categories: StateFlow<CategoryState> = categoriesFlow
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), CategoryState())
    private val mutableState = MutableStateFlow(DraftState())
    val state: StateFlow<DraftState> = mutableState.asStateFlow()
    private val writes = Mutex()
    private var inputJob: Job? = null
    private var pollJob: Job? = null
    private var parsedUrls = ""
    private var hasLoaded = false
    private val probes = mutableMapOf<String, Job>()
    private val attempted = mutableSetOf<String>()

    init { refresh() }

    fun setUrls(urls: String) {
        if (state.value.isWorking) return
        mutableState.value = state.value.copy(urls = urls)
        inputJob?.cancel()
        inputJob = viewModelScope.launch {
            delay(1000)
            run { writes.withLock { withContext(NonCancellable) { parseInput() } } }
            refresh()
        }
    }

    private suspend fun parseInput() {
        val urls = state.value.urls.trim()
        if (urls == parsedUrls) return
        send("parse", listOf(urls))
        parsedUrls = urls
        val current = urls.lines().map(String::trim).toSet()
        attempted.retainAll(current)
        probes.keys.toList().filterNot { it in current }.forEach { probes.remove(it)?.cancel() }
        mutableState.value = state.value.copy(
            probing = state.value.probing.intersect(current),
            probeErrors = state.value.probeErrors.filterKeys { it in current },
        )
        load()
    }

    private suspend fun load() {
        val items = fetchItems()
        if (!hasLoaded && state.value.urls.isEmpty()) {
            parsedUrls = items.joinToString("\n") { it.url }
            mutableState.value = state.value.copy(urls = parsedUrls)
        }
        hasLoaded = true
        mutableState.value = state.value.copy(items = items)
        items.filter { it.canProbeMedia && !it.hasMediaInfo && it.url !in attempted }
            .forEach { probe(it.url, "media") }
    }

    fun refresh() {
        if (pollJob?.isActive == true) return
        pollJob = viewModelScope.launch {
            do {
                run { writes.withLock { load() } }
                delay(500)
            } while (isActive && (state.value.items.any(DraftItem::isParsing) || probes.isNotEmpty()))
        }
    }

    fun probe(url: String, kind: String) {
        if (url in probes || state.value.isWorking) return
        attempted.add(url)
        mutableState.value = state.value.copy(
            probing = state.value.probing + url,
            probeErrors = state.value.probeErrors - url,
        )
        val job = viewModelScope.launch(start = CoroutineStart.LAZY) {
            try {
                send("probeDraft", listOf(url, kind))
                writes.withLock { load() }
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                mutableState.value = state.value.copy(
                    probeErrors = state.value.probeErrors + (url to DraftProbeError(kind, error.message ?: error.toString())),
                )
            } finally {
                if (probes[url] === coroutineContext[Job]) {
                    probes.remove(url)
                    mutableState.value = state.value.copy(probing = state.value.probing - url)
                }
            }
        }
        probes[url] = job
        job.start()
    }

    suspend fun setCategory(url: String, choice: String?): Boolean =
        update(url, listOf(DraftChange("setCategory", listOf(choice.orEmpty(), choice == null))))

    suspend fun update(url: String, changes: List<DraftChange>): Boolean = runWorking {
        writes.withLock {
            changes.forEach { change ->
                send("setDraft", listOf(url, change.action) + change.arguments)
            }
            load()
        }
    }

    suspend fun confirm(): Boolean = runWorking {
        inputJob?.cancel()
        writes.withLock {
            parseInput()
            load()
            check(state.value.items.any { it.error == null }) { "No task to confirm" }
            send("confirmDraft", emptyList())
            stop()
        }
    }

    suspend fun cancel(): Boolean = runWorking {
        inputJob?.cancel()
        writes.withLock {
            send("clearDraft", emptyList())
            stop()
        }
    }

    private fun stop() {
        pollJob?.cancel()
        probes.values.toList().forEach(Job::cancel)
        probes.clear()
        attempted.clear()
        parsedUrls = ""
        mutableState.value = DraftState(isWorking = true)
    }

    private suspend fun runWorking(block: suspend () -> Unit): Boolean {
        if (state.value.isWorking) return false
        mutableState.value = state.value.copy(isWorking = true, error = null)
        return try { withContext(NonCancellable) { run(block) } } finally {
            mutableState.value = state.value.copy(isWorking = false)
        }
    }

    private suspend fun run(block: suspend () -> Unit): Boolean = try {
        block()
        true
    } catch (error: CancellationException) {
        throw error
    } catch (error: Exception) {
        mutableState.value = state.value.copy(error = error.message ?: error.toString())
        false
    }
}
