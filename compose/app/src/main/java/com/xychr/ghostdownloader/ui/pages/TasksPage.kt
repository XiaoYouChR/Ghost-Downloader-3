package com.xychr.ghostdownloader.ui.pages

import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.navigation.*
import com.xychr.ghostdownloader.ui.components.*
import com.xychr.ghostdownloader.ui.components.task.*
import com.xychr.ghostdownloader.ui.platform.openTaskFile

import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.ExperimentalFoundationApi

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.ui.navigation.DRAFT_CONTAINER
import com.xychr.ghostdownloader.ui.navigation.DraftRoute
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.navigation.Route
import com.xychr.ghostdownloader.ui.navigation.TaskDetailRoute
import com.xychr.ghostdownloader.ui.navigation.TaskFilesRoute
import com.xychr.ghostdownloader.ui.navigation.TaskEditRoute
import com.xychr.ghostdownloader.ui.navigation.sharedContainer
import com.xychr.ghostdownloader.ui.components.liquid.LiquidAddButton
import com.xychr.ghostdownloader.ui.components.category.CategoryFilter
import com.xychr.ghostdownloader.ui.components.category.CategorySheet
import com.kyant.backdrop.backdrops.layerBackdrop
import com.kyant.backdrop.backdrops.rememberLayerBackdrop
import com.xychr.ghostdownloader.packs.PackRegistry
import kotlinx.coroutines.launch

private data class TaskSections(val active: List<TaskUiState>, val completed: List<TaskUiState>)

private fun buildTaskSections(tasks: List<TaskUiState>, heldSections: Map<String, Boolean>): TaskSections {
    val (completed, active) = tasks.partition { heldSections[it.id] ?: it.isFinished }
    return TaskSections(active, completed)
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
fun TasksPage(
    onNavigate: (Route) -> Unit,
    onManageCategories: () -> Unit,
    bottomContentPadding: Dp = 0.dp,
    viewModel: TaskViewModel = viewModel(),
) {
    val taskState by viewModel.state.collectAsStateWithLifecycle()
    val allTasks = taskState.tasks
    val categoryState by viewModel.categories.collectAsStateWithLifecycle()
    var categoryFilter by rememberSaveable { mutableStateOf<String?>(null) }
    var categoryTaskIds by remember { mutableStateOf<List<String>>(emptyList()) }
    LaunchedEffect(categoryState) {
        if (!categoryState.isEnabled || categoryFilter?.let { it.isNotEmpty() &&
            categoryState.categories.none { category -> category.categoryId == it } } == true) categoryFilter = null
    }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }
    val contentBackdrop = rememberLayerBackdrop()

    val selection = remember { SelectionState() }
    var isActiveOpen by rememberSaveable { mutableStateOf(true) }
    var isCompletedOpen by rememberSaveable { mutableStateOf(true) }
    var expandedId by rememberSaveable { mutableStateOf<String?>(null) }
    var expandedSection by rememberSaveable { mutableStateOf(false) }
    var selectedSections by remember { mutableStateOf<Map<String, Boolean>>(emptyMap()) }
    var sortField by rememberSaveable { mutableStateOf(SortField.CREATED) }
    var isDescending by rememberSaveable { mutableStateOf(true) }
    var query by rememberSaveable { mutableStateOf("") }
    var isSearching by rememberSaveable { mutableStateOf(false) }
    var deleteIds by remember { mutableStateOf<List<String>>(emptyList()) }
    var redownloadIds by remember { mutableStateOf<List<String>>(emptyList()) }

    val visibleTasks = remember(allTasks, query, isSearching, sortField, isDescending, categoryFilter, categoryState) {
        allTasks.buildTaskOrder(if (isSearching) query else "", sortField, isDescending)
            .filter { categoryFilter == null || toCategoryId(it.categoryId, categoryState.categories) == categoryFilter }
    }
    val sections = buildTaskSections(visibleTasks, when {
        selection.isActive -> selectedSections
        expandedId != null -> mapOf(expandedId!! to expandedSection)
        else -> emptyMap()
    })
    LaunchedEffect(allTasks.map { it.id }) {
        selection.update(allTasks.map { it.id })
        if (allTasks.none { it.id == expandedId }) expandedId = null
    }

    val topBarState = when {
        selection.isActive -> TopBarMode.SELECTING
        isSearching -> TopBarMode.SEARCHING
        else -> TopBarMode.NORMAL
    }

    val keyboard = androidx.compose.ui.platform.LocalSoftwareKeyboardController.current
    var isSubmitting by remember { mutableStateOf(false) }
    val actionTasks = if (selection.isActive) allTasks.filter { it.id in selection.selectedIds } else allTasks
    val targets = buildTaskBatchTargets(actionTasks)

    fun closeSearch() {
        keyboard?.hide()
        isSearching = false
        query = ""
    }

    BackHandler(enabled = expandedId != null && !selection.isActive && !isSearching) { expandedId = null }
    BackHandler(enabled = selection.isActive) { selection.exit() }
    BackHandler(enabled = isSearching && !selection.isActive) { closeSearch() }

    Scaffold(
        topBar = {
            TasksTopBar(
                state = TaskTopBarState(
                    mode = topBarState, query = query, summary = buildTaskSummary(allTasks),
                    readState = taskState.readState, targets = targets, taskCount = visibleTasks.size,
                    selectedCount = selection.count, isCategoryEnabled = categoryState.isEnabled,
                    isSubmitting = isSubmitting, sortField = sortField, isDescending = isDescending,
                ),
                onQueryChange = { query = it },
                onSort = { field, descending -> sortField = field; isDescending = descending },
                onAction = { action ->
                    when (action) {
                        TaskPageAction.SEARCH -> isSearching = true
                        TaskPageAction.CLOSE_SEARCH -> closeSearch()
                        TaskPageAction.CLOSE_SELECTION -> selection.exit()
                        TaskPageAction.SELECT -> {
                            keyboard?.hide()
                            selectedSections = allTasks.associate { it.id to it.isFinished }
                            expandedId = null
                            selection.start()
                        }
                        TaskPageAction.START, TaskPageAction.PAUSE -> if (!isSubmitting) {
                            val batchAction = if (action == TaskPageAction.START) TaskBatchAction.START else TaskBatchAction.PAUSE
                            val ids = if (batchAction == TaskBatchAction.START) targets.startIds
                                else actionTasks.filter { it.status == TaskStatus.RUNNING || it.status == TaskStatus.WAITING }.map { it.id }
                            isSubmitting = true
                            scope.launch {
                                val result = try {
                                    viewModel.requestBatch(batchAction, ids)
                                } finally { isSubmitting = false }
                                snackbarHostState.showSnackbar(context.getString(
                                    if (batchAction == TaskBatchAction.START) R.string.task_bar_start_result else R.string.task_bar_pause_result,
                                    result.submitted, result.failed, result.skipped))
                            }
                        }
                        TaskPageAction.MANAGE_CATEGORIES -> onManageCategories()
                        TaskPageAction.CATEGORIZE -> categoryTaskIds = selection.selectedIds.toList()
                        TaskPageAction.DELETE -> deleteIds = selection.selectedIds.toList()
                        TaskPageAction.COPY -> {
                            val urls = allTasks.filter { it.id in selection.selectedIds }.map { it.url }.filter(String::isNotEmpty)
                            if (urls.isNotEmpty()) {
                                context.getSystemService(ClipboardManager::class.java)
                                    .setPrimaryClip(ClipData.newPlainText("url", urls.joinToString("\n")))
                                scope.launch { snackbarHostState.showSnackbar(context.getString(R.string.task_copied_urls, urls.size)) }
                            }
                        }
                        TaskPageAction.MOVE_TO_FRONT -> viewModel.moveToFrontEach(selection.selectedIds)
                        TaskPageAction.REDOWNLOAD -> redownloadIds = selection.selectedIds.toList()
                        TaskPageAction.SELECT_ALL -> selection.selectAll(visibleTasks.filter {
                            isSearching || if (selectedSections[it.id] ?: it.isFinished) isCompletedOpen else isActiveOpen
                        }.map { it.id })
                        TaskPageAction.INVERT_SELECTION -> selection.invert(visibleTasks.filter {
                            isSearching || if (selectedSections[it.id] ?: it.isFinished) isCompletedOpen else isActiveOpen
                        }.map { it.id })
                    }
                },
            )
        },
        floatingActionButton = {
            AnimatedVisibility(
                visible = !selection.isActive,
                enter = fadeIn(),
                exit = fadeOut(),
            ) {
                LiquidAddButton(
                    onClick = { onNavigate(DraftRoute) },
                    backdrop = contentBackdrop,
                    modifier = Modifier.padding(bottom = bottomContentPadding).sharedContainer(DRAFT_CONTAINER),
                )
            }
        },
        snackbarHost = { SnackbarHost(snackbarHostState, Modifier.padding(bottom = bottomContentPadding)) },
    ) { padding ->
        Column(Modifier.padding(padding).consumeWindowInsets(padding)
            .layerBackdrop(contentBackdrop).background(MaterialTheme.colorScheme.background)) {
            if (categoryState.isEnabled) CategoryFilter(categoryFilter, categoryState.categories,
                { categoryFilter = it }, Modifier.padding(horizontal = 12.dp))
            if (visibleTasks.isEmpty()) {
                if (taskState.readState != TaskReadState.READY) Box(Modifier.weight(1f).fillMaxWidth())
                else if (categoryFilter != null) Column(Modifier.weight(1f).fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text(stringResource(R.string.task_category_empty), Modifier.padding(24.dp))
                    TextButton(onClick = { categoryFilter = null }) { Text(stringResource(R.string.task_clear_category_filter)) }
                } else EmptyState(isSearching && query.isNotBlank(),
                    Modifier.weight(1f).padding(bottom = bottomContentPadding))
            } else {
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(
                        start = 12.dp, end = 12.dp, top = 8.dp,
                        bottom = 80.dp + bottomContentPadding,
                    ),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    listOf(false to sections.active, true to sections.completed).forEach { (isCompleted, tasks) ->
                        val isOpen = isSearching || if (isCompleted) isCompletedOpen else isActiveOpen
                        stickyHeader(key = "section-$isCompleted") {
                            TaskSection(isCompleted, tasks.size, isOpen) {
                                if (!isSearching) {
                                    if (isCompleted) isCompletedOpen = !isCompletedOpen else isActiveOpen = !isActiveOpen
                                    if (expandedSection == isCompleted) expandedId = null
                                }
                            }
                        }
                        if (isOpen) items(tasks, key = { it.id }) { task ->
                            TaskCard(
                                task = task,
                                isSelecting = selection.isActive,
                                isSelected = task.id in selection.selectedIds,
                                isExpanded = expandedId == task.id,
                                category = categoryState.categories.firstOrNull { it.categoryId == task.categoryId },
                                isCategoryEnabled = categoryState.isEnabled,
                                packExtra = PackRegistry[task.packId]?.taskExtra,
                                onClick = {
                                    if (selection.isActive) selection.toggle(task.id)
                                    else {
                                        expandedSection = isCompleted
                                        expandedId = if (expandedId == task.id) null else task.id
                                    }
                                },
                                onLongClick = {
                                    if (selection.isActive) selection.toggle(task.id)
                                    else {
                                        selectedSections = allTasks.associate { it.id to it.isFinished } +
                                            listOfNotNull(expandedId?.let { it to expandedSection }).toMap()
                                        expandedId = null
                                        keyboard?.hide()
                                        selection.enter(task.id)
                                    }
                                },
                                onAction = { action ->
                                    when (action) {
                                        TaskAction.RUN -> when {
                                            task.canStop -> viewModel.stop(task.id)
                                            task.status == TaskStatus.RUNNING -> viewModel.pause(task.id)
                                            else -> viewModel.resume(task.id)
                                        }
                                        TaskAction.DETAILS -> onNavigate(TaskDetailRoute(task.id))
                                        TaskAction.FILES -> onNavigate(TaskFilesRoute(task.id))
                                        TaskAction.EDIT -> onNavigate(TaskEditRoute(task.id))
                                        TaskAction.CATEGORY -> categoryTaskIds = listOf(task.id)
                                        TaskAction.OPEN_FILE -> {
                                            if (task.hasOutputFile) context.openTaskFile(task.outputPath)
                                            else onNavigate(TaskDetailRoute(task.id))
                                        }
                                        TaskAction.COPY_URL -> {
                                            context.getSystemService(ClipboardManager::class.java)
                                                .setPrimaryClip(ClipData.newPlainText("url", task.url))
                                            scope.launch { snackbarHostState.showSnackbar(context.getString(R.string.task_detail_copied)) }
                                        }
                                        TaskAction.MOVE_TO_FRONT -> viewModel.moveToFront(task.id)
                                        TaskAction.DELETE -> deleteIds = listOf(task.id)
                                        TaskAction.REDOWNLOAD -> redownloadIds = listOf(task.id)
                                    }
                                },
                                modifier = Modifier.animateItem(),
                            )
                        }
                    }
                }
            }
        }
    }

    if (deleteIds.isNotEmpty()) {
        DeleteTasksDialog(
            count = deleteIds.size,
            onDismiss = { deleteIds = emptyList() },
            onConfirm = { shouldDeleteFiles ->
                viewModel.removeEach(deleteIds, shouldDeleteFiles)
                selection.exit()
                deleteIds = emptyList()
            },
        )
    }
    if (categoryTaskIds.isNotEmpty()) CategorySheet(categoryState.categories,
        initialCategoryId = allTasks.filter { it.id in categoryTaskIds }
            .map { toCategoryId(it.categoryId, categoryState.categories) }.distinct().singleOrNull(),
        taskCount = categoryTaskIds.size,
        onApply = { categoryId ->
            viewModel.setCategory(categoryTaskIds, categoryId)
            selection.exit()
            val name = categoryState.categories.firstOrNull { it.categoryId == categoryId }?.name
                ?: context.getString(R.string.task_uncategorized)
            scope.launch { snackbarHostState.showSnackbar(context.getString(R.string.task_category_applied, name)) }
        }, onDismiss = { categoryTaskIds = emptyList() })
    if (redownloadIds.isNotEmpty()) {
        AlertDialog(
            onDismissRequest = { redownloadIds = emptyList() },
            title = { Text(stringResource(R.string.task_detail_redownload)) },
            text = { Text(stringResource(R.string.task_redownload_warning)) },
            confirmButton = { TextButton(onClick = {
                viewModel.redownloadEach(redownloadIds)
                redownloadIds = emptyList()
                selection.exit()
            }) { Text(stringResource(R.string.task_detail_redownload)) } },
            dismissButton = { TextButton(onClick = { redownloadIds = emptyList() }) {
                Text(stringResource(R.string.action_cancel))
            } },
        )
    }
}

/** 过滤、搜索、排序合成一步——中间结果没人要，拆开只会多出两个临时列表 */
private fun List<TaskUiState>.buildTaskOrder(
    query: String,
    sortField: SortField,
    isDescending: Boolean,
): List<TaskUiState> {
    val matched = filter { task ->
        val matchesQuery = query.isBlank() ||
            task.name.contains(query, ignoreCase = true) ||
            task.url.contains(query, ignoreCase = true)
        matchesQuery
    }
    val sorted = when (sortField) {
        SortField.CREATED -> matched.sortedBy { it.createdAt }
        SortField.COMPLETED -> matched.sortedBy { it.completedAt }
        SortField.NAME -> matched.sortedBy { it.name.lowercase() }
        SortField.SIZE -> matched.sortedBy { it.fileSize }
        SortField.QUEUE -> matched.sortedBy { it.queueRank }
    }
    return if (isDescending) sorted.reversed() else sorted
}

private val TaskUiState.queueRank: Int
    get() = when (status) {
        TaskStatus.RUNNING -> 0
        TaskStatus.WAITING -> 1
        TaskStatus.PAUSED -> 2
        else -> 3
    }

@Composable
private fun TaskSection(isCompleted: Boolean, count: Int, isOpen: Boolean, onClick: () -> Unit) {
    val state = stringResource(if (isOpen) R.string.task_expanded else R.string.task_collapsed)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .semantics { heading(); stateDescription = state }
            .clickable(onClick = onClick)
            .heightIn(min = 48.dp)
            .padding(horizontal = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(stringResource(if (isCompleted) R.string.task_filter_completed else R.string.task_unfinished),
            style = MaterialTheme.typography.titleSmall)
        Text("  $count", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.weight(1f))
        Text(if (isOpen) "−" else "+", style = MaterialTheme.typography.titleLarge)
    }
}

@Composable
private fun EmptyState(isSearchEmpty: Boolean, modifier: Modifier = Modifier) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = stringResource(if (isSearchEmpty) R.string.task_search_empty else R.string.task_empty_title),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = stringResource(if (isSearchEmpty) R.string.task_search_change else R.string.task_empty_hint),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun DeleteTasksDialog(count: Int, onDismiss: () -> Unit, onConfirm: (Boolean) -> Unit) {
    var shouldDeleteFiles by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.task_delete_count, count)) },
        text = {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .toggleable(
                        value = shouldDeleteFiles,
                        role = Role.Checkbox,
                        onValueChange = { shouldDeleteFiles = it },
                    ),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Checkbox(checked = shouldDeleteFiles, onCheckedChange = null)
                Text(
                    text = stringResource(R.string.task_detail_delete_files),
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(shouldDeleteFiles) }) {
                Text(
                    text = stringResource(R.string.action_delete),
                    color = MaterialTheme.colorScheme.error,
                )
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) }
        },
    )
}
