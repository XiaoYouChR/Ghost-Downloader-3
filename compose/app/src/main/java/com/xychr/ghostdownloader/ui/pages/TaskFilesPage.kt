package com.xychr.ghostdownloader.ui.pages

import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.components.SelectableFile
import com.xychr.ghostdownloader.ui.components.SelectableFileList
import com.xychr.ghostdownloader.ui.components.task.*

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.ErrorText
import com.xychr.ghostdownloader.i18n.toTaskError
import com.xychr.ghostdownloader.model.Category
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

data class TaskFilesState(
    val detail: TaskDetail? = null,
    val files: List<TaskFile> = emptyList(),
    val selected: Set<Int> = emptySet(),
    val initial: Set<Int> = emptySet(),
    val isSaving: Boolean = false,
    val isDone: Boolean = false,
    val needsDownload: Boolean = false,
    val error: TaskError? = null,
) {
    val hasChanges get() = selected != initial || files != detail?.files.orEmpty()
}

@Serializable
data class TaskFileEdits(
    val selected: List<Int>,
    val trim: Map<String, List<Int>> = emptyMap(),
    val titles: Map<String, String> = emptyMap(),
)

class TaskFilesViewModel(
    private val fetch: suspend () -> TaskDetail,
    private val send: suspend (TaskFileEdits) -> Unit,
) : ViewModel() {
    private val mutableState = MutableStateFlow(TaskFilesState())
    val state = mutableState.asStateFlow()

    init { refresh() }

    fun refresh() {
        viewModelScope.launch {
            try {
                val detail = fetch()
                check(detail.id.isNotEmpty()) { "Task no longer exists" }
                val indexes = detail.files.filter { it.isSelected }.map { it.index }.toSet()
                mutableState.value = TaskFilesState(detail, detail.files, indexes, indexes)
            } catch (error: Exception) {
                mutableState.value = mutableState.value.copy(error = error.toTaskError())
            }
        }
    }

    fun setSelection(indexes: Set<Int>) {
        if (!state.value.isSaving) mutableState.value = state.value.copy(selected = indexes, error = null)
    }

    fun setTrim(index: Int, start: Int, end: Int) {
        if (state.value.isSaving) return
        mutableState.value = state.value.copy(
            files = state.value.files.map {
                if (it.index == index) it.copy(startTime = start, endTime = end) else it
            },
            error = null,
        )
    }

    fun setTitle(index: Int, newPath: String) {
        if (state.value.isSaving) return
        mutableState.value = state.value.copy(
            files = state.value.files.map { if (it.index == index) it.copy(path = newPath) else it },
            error = null,
        )
    }

    fun cancelConfirmation() { mutableState.value = state.value.copy(needsDownload = false) }

    fun save(shouldDownload: Boolean = false) {
        val before = state.value
        if (before.isSaving || !before.hasChanges || before.selected.isEmpty()) return
        mutableState.value = before.copy(isSaving = true, error = null, needsDownload = false)
        viewModelScope.launch {
            try {
                val current = fetch()
                check(current.id.isNotEmpty()) { "Task no longer exists" }
                check(before.selected.all { index -> current.files.any { it.index == index } }) {
                    "Task files changed; reopen file selection"
                }
                if (!shouldDownload && current.status == TaskStatus.COMPLETED &&
                    current.files.any { it.index in before.selected && !it.isCompleted }) {
                    mutableState.value = state.value.copy(isSaving = false, needsDownload = true)
                    return@launch
                }
                val originals = before.detail?.files.orEmpty().associateBy { it.index }
                send(TaskFileEdits(
                    selected = before.selected.sorted(),
                    trim = before.files.filter { it.startTime != null }
                        .associate { "${it.index}" to listOf(it.startTime ?: 0, it.endTime ?: 0) },
                    titles = before.files.filter { originals[it.index]?.path != it.path }
                        .associate { "${it.index}" to it.path.substringAfterLast('/') },
                ))
                mutableState.value = state.value.copy(isSaving = false, isDone = true)
            } catch (error: Exception) {
                mutableState.value = state.value.copy(isSaving = false, error = error.toTaskError())
            }
        }
    }
}

@Composable
fun TaskFilesPage(taskId: String, onBack: () -> Unit, categories: CategoryState = CategoryState()) {
    val model: TaskFilesViewModel = viewModel(key = taskId) {
        TaskFilesViewModel(
            fetch = { engineRepository.query("taskDetail", taskId) },
            send = { engineRepository.invoke("applyTaskFileEdits", taskId, engineRepository.encode(it)) },
        )
    }
    val state by model.state.collectAsStateWithLifecycle()
    LaunchedEffect(state.isDone) { if (state.isDone) onBack() }
    TaskFilesEditor(state, model::setSelection, { model.save() }, onBack,
        onRetry = model::refresh, onTrim = model::setTrim, onRename = model::setTitle, categories = categories)
    if (state.needsDownload) AlertDialog(
        onDismissRequest = model::cancelConfirmation,
        title = { Text(stringResource(R.string.task_apply_download)) },
        text = { Text(stringResource(R.string.task_selection_revive)) },
        confirmButton = { TextButton(onClick = { model.save(true) }) {
            Text(stringResource(R.string.task_apply_download))
        } },
        dismissButton = { TextButton(onClick = model::cancelConfirmation) {
            Text(stringResource(R.string.action_cancel))
        } },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskFilesEditor(
    state: TaskFilesState,
    onSelection: (Set<Int>) -> Unit,
    onSave: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    onRetry: () -> Unit = {},
    onTrim: (Int, Int, Int) -> Unit = { _, _, _ -> },
    onRename: (Int, String) -> Unit = { _, _ -> },
    categories: CategoryState = CategoryState(),
) {
    var shouldDiscard by remember { mutableStateOf(false) }
    val close = { if (state.hasChanges) shouldDiscard = true else onBack() }
    BackHandler { if (!state.isSaving) close() }
    Scaffold(modifier = modifier, topBar = {
        TopAppBar(title = { Text(stringResource(R.string.task_choose_files)) },
            navigationIcon = { IconButton(onClick = close, enabled = !state.isSaving) {
                Icon(painterResource(R.drawable.ic_arrow_back), stringResource(R.string.action_back))
            } }, actions = {
                TextButton(onClick = onSave, enabled = state.hasChanges && state.selected.isNotEmpty() && !state.isSaving) {
                    Text(stringResource(R.string.task_apply))
                }
            })
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            if (state.isSaving) LinearProgressIndicator(Modifier.fillMaxWidth())
            ErrorText(state.error, Modifier.padding(16.dp))
            val detail = state.detail
            if (detail == null) {
                if (state.error == null) CircularProgressIndicator(Modifier.padding(16.dp))
                else TextButton(onClick = onRetry) { Text(stringResource(R.string.task_retry)) }
            } else {
                Text(detail.name, Modifier.padding(16.dp), style = MaterialTheme.typography.titleMedium)
                Text(stringResource(R.string.task_selected_files, state.selected.size, state.files.size),
                    Modifier.padding(horizontal = 16.dp))
                if (categories.isEnabled) FileCategoryMenu(state.files, categories.categories,
                    onSelection, isEnabled = !state.isSaving)
                SelectableFileList(
                    files = remember(state.files) {
                        state.files.map {
                            SelectableFile(it.index, it.path, it.groups, it.size, it.startTime, it.endTime)
                        }
                    },
                    selectedIndexes = state.selected,
                    onSelectionChange = onSelection,
                    onRename = onRename,
                    onTrim = onTrim,
                    isEnabled = !state.isSaving,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
    if (shouldDiscard) DiscardTaskChanges(onDismiss = { shouldDiscard = false }, onDiscard = onBack)
}

@Composable
fun DiscardTaskChanges(onDismiss: () -> Unit, onDiscard: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.task_discard_changes)) },
        text = { Text(stringResource(R.string.task_unsaved_changes)) },
        confirmButton = { TextButton(onClick = onDiscard) { Text(stringResource(R.string.task_discard)) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) } },
    )
}

@Composable
private fun FileCategoryMenu(files: List<TaskFile>, categories: List<Category>, onSelect: (Set<Int>) -> Unit,
                             modifier: Modifier = Modifier, isEnabled: Boolean = true) {
    var isOpen by remember { mutableStateOf(false) }
    val choices = listOf(Category(name = stringResource(R.string.task_uncategorized))) + categories
    val filesByCategory = remember(files, categories) {
        files.groupBy { it.categoryId }
    }
    Column(modifier.padding(horizontal = 16.dp)) {
        Box {
            TextButton(onClick = { isOpen = true }, enabled = isEnabled) {
                Text(stringResource(R.string.task_select_category_files))
            }
            DropdownMenu(expanded = isOpen && isEnabled, onDismissRequest = { isOpen = false }) {
                choices.forEach { category ->
                    val matches = filesByCategory[category.categoryId].orEmpty()
                    DropdownMenuItem(text = {
                        Text(stringResource(R.string.task_select_category_count, category.name, matches.size))
                    }, enabled = matches.isNotEmpty(), onClick = {
                        isOpen = false
                        onSelect(matches.map { it.index }.toSet())
                    })
                }
            }
        }
        Text(stringResource(R.string.task_select_category_hint), style = MaterialTheme.typography.bodySmall)
    }
}
