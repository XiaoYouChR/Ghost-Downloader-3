package com.xychr.ghostdownloader.ui.pages

import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.components.*
import com.xychr.ghostdownloader.ui.components.task.*
import com.xychr.ghostdownloader.ui.util.*

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.Category
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class TaskFilesState(
    val detail: TaskDetail? = null,
    val selected: Set<Int> = emptySet(),
    val initial: Set<Int> = emptySet(),
    val isSaving: Boolean = false,
    val isDone: Boolean = false,
    val needsDownload: Boolean = false,
    val error: String? = null,
) {
    val hasChanges get() = selected != initial
}

class TaskFilesViewModel(
    private val fetch: suspend () -> TaskDetail,
    private val send: suspend (Set<Int>) -> Unit,
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
                mutableState.value = TaskFilesState(detail, indexes, indexes)
            } catch (error: Exception) {
                mutableState.value = mutableState.value.copy(error = error.message)
            }
        }
    }

    fun setSelection(indexes: Set<Int>) {
        if (!state.value.isSaving) mutableState.value = state.value.copy(selected = indexes, error = null)
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
                send(before.selected)
                mutableState.value = state.value.copy(isSaving = false, isDone = true)
            } catch (error: Exception) {
                mutableState.value = state.value.copy(isSaving = false, error = error.message)
            }
        }
    }
}

@Composable
fun TaskFilesPage(taskId: String, onBack: () -> Unit, categories: CategoryState = CategoryState()) {
    val model: TaskFilesViewModel = viewModel(key = taskId) {
        TaskFilesViewModel(
            fetch = { EngineRepository.query("taskDetail", taskId) },
            send = { EngineRepository.invoke("setTaskSelection", taskId, it.sorted().joinToString(",")) },
        )
    }
    val state by model.state.collectAsStateWithLifecycle()
    LaunchedEffect(state.isDone) { if (state.isDone) onBack() }
    TaskFilesEditor(state, model::setSelection, { model.save() }, onBack, onRetry = model::refresh, categories = categories)
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
        LazyColumn(Modifier.fillMaxSize().padding(padding)) {
            item {
                if (state.isSaving) LinearProgressIndicator(Modifier.fillMaxWidth())
                state.error?.let { Text(it, Modifier.padding(16.dp), color = MaterialTheme.colorScheme.error) }
                if (state.detail == null) {
                    if (state.error == null) CircularProgressIndicator(Modifier.padding(16.dp))
                    else TextButton(onClick = onRetry) { Text(stringResource(R.string.task_retry)) }
                }
            }
            state.detail?.let { detail ->
                item {
                    Text(detail.name, Modifier.padding(16.dp), style = MaterialTheme.typography.titleMedium)
                    Text(stringResource(R.string.task_selected_files, state.selected.size, detail.files.size), Modifier.padding(horizontal = 16.dp))
                    Row {
                        TextButton(onClick = { onSelection(detail.files.map { it.index }.toSet()) }, enabled = !state.isSaving) {
                            Text(stringResource(R.string.task_select_all))
                        }
                        TextButton(onClick = { onSelection(detail.files.map { it.index }.toSet() - state.selected) }, enabled = !state.isSaving) {
                            Text(stringResource(R.string.task_select_invert))
                        }
                    }
                    if (categories.isEnabled) FileCategoryMenu(detail.files, categories.categories,
                        onSelection, isEnabled = !state.isSaving)
                }
                items(detail.files, key = { it.index }) { file ->
                    val isSelected = file.index in state.selected
                    ListItem(
                        supportingContent = { Text(formatSize(file.size)) },
                        leadingContent = { Checkbox(isSelected, onCheckedChange = null) },
                        modifier = Modifier.toggleable(isSelected, enabled = !state.isSaving, role = Role.Checkbox) {
                            onSelection(if (it) state.selected + file.index else state.selected - file.index)
                        },
                    ) { Text(file.path) }
                }
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
        files.groupBy { toCategoryId(it.categoryId, categories) }
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
