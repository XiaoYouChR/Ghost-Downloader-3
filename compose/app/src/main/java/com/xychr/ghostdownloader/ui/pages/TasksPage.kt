package com.xychr.ghostdownloader.ui.pages

import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.navigation.*
import com.xychr.ghostdownloader.ui.components.*
import com.xychr.ghostdownloader.ui.components.task.*
import com.xychr.ghostdownloader.ui.platform.openFolder
import com.xychr.ghostdownloader.ui.platform.openTaskFile
import com.xychr.ghostdownloader.ui.platform.shareTaskFile
import com.xychr.ghostdownloader.ui.platform.shareText

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.heightIn
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
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
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
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.ui.components.notice.LocalSnackbar
import com.xychr.ghostdownloader.ui.navigation.Route
import com.xychr.ghostdownloader.ui.navigation.TaskDetailRoute
import com.xychr.ghostdownloader.ui.navigation.TaskFilesRoute
import com.xychr.ghostdownloader.ui.navigation.TaskEditRoute
import com.xychr.ghostdownloader.ui.navigation.sharedContainer
import com.xychr.ghostdownloader.ui.components.liquid.LiquidAddButton
import com.xychr.ghostdownloader.ui.components.category.CategoryFilterRow
import com.xychr.ghostdownloader.ui.components.category.CategoryPicker
import com.kyant.backdrop.backdrops.layerBackdrop
import com.kyant.backdrop.backdrops.rememberLayerBackdrop
import com.xychr.ghostdownloader.packs.PackRegistry
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
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
    val snackbarHostState = LocalSnackbar.current
    val contentBackdrop = rememberLayerBackdrop()

    val selection = remember { SelectionState() }
    var isActiveOpen by rememberSaveable { mutableStateOf(true) }
    var isCompletedOpen by rememberSaveable { mutableStateOf(true) }
    var selectedSections by remember { mutableStateOf<Map<String, Boolean>>(emptyMap()) }
    var sortField by rememberSaveable { mutableStateOf(SortField.CREATED) }
    var isDescending by rememberSaveable { mutableStateOf(true) }
    var query by rememberSaveable { mutableStateOf("") }
    var isSearching by rememberSaveable { mutableStateOf(false) }
    var deleteIds by remember { mutableStateOf<List<String>>(emptyList()) }
    var redownloadIds by remember { mutableStateOf<List<String>>(emptyList()) }
    var hashTask by remember { mutableStateOf<TaskUiState?>(null) }

    val visibleTasks = remember(allTasks, query, isSearching, sortField, isDescending, categoryFilter) {
        buildTaskOrder(allTasks, if (isSearching) query else "", categoryFilter, sortField, isDescending)
    }
    val sections = buildTaskSections(visibleTasks, if (selection.isActive) selectedSections else emptyMap())
    LaunchedEffect(allTasks.map { it.id }) { selection.update(allTasks.map { it.id }) }

    val keyboard = LocalSoftwareKeyboardController.current
    var isSubmitting by remember { mutableStateOf(false) }
    val actionTasks = if (selection.isActive) allTasks.filter { it.id in selection.selectedIds } else allTasks
    val targets = buildTaskBatchTargets(actionTasks)
    val openSectionIds = visibleTasks.filter {
        isSearching || if (selectedSections[it.id] ?: it.isFinished) isCompletedOpen else isActiveOpen
    }.map { it.id }

    fun closeSearch() {
        keyboard?.hide()
        isSearching = false
        query = ""
    }

    fun startSelection(taskId: String? = null) {
        keyboard?.hide()
        selectedSections = allTasks.associate { it.id to it.isFinished }
        selection.start(taskId)
    }

    fun runPageAction(action: TaskPageAction) {
        when (action) {
            TaskPageAction.SEARCH -> isSearching = true
            TaskPageAction.CLOSE_SEARCH -> closeSearch()
            TaskPageAction.CLOSE_SELECTION -> selection.clear()
            TaskPageAction.SELECT -> startSelection()
            TaskPageAction.START -> if (selection.isActive) viewModel.resumeEach(targets.startIds)
            else viewModel.startAll()
            TaskPageAction.PAUSE -> if (!isSubmitting) {
                isSubmitting = true
                scope.launch {
                    try { viewModel.pauseEach(targets.pauseIds) }
                    finally { isSubmitting = false }
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
            TaskPageAction.MOVE_TO_FRONT -> viewModel.moveToFront(selection.selectedIds)
            TaskPageAction.REDOWNLOAD -> redownloadIds = selection.selectedIds.toList()
            TaskPageAction.SELECT_ALL -> selection.selectAll(openSectionIds)
            TaskPageAction.INVERT_SELECTION -> selection.invert(openSectionIds)
            TaskPageAction.SELECT_MISSING -> {
                val ids = openSectionIds.toSet()
                val missing = allTasks.filter { it.isFileMissing && it.id in ids }.map { it.id }
                if (missing.isEmpty()) selection.clear() else selection.selectAll(missing)
            }
        }
    }

    BackHandler(enabled = selection.isActive) { selection.clear() }
    BackHandler(enabled = isSearching) { closeSearch() }

    Scaffold(
        topBar = {
            TasksTopBar(
                state = TaskTopBarState(
                    isSelecting = selection.isActive, isSearching = isSearching, query = query,
                    selectedCount = selection.count, taskCount = visibleTasks.size,
                    hasLoaded = taskState.hasLoaded, speed = buildTotalSpeed(allTasks),
                    targets = targets,
                    isSubmitting = isSubmitting, sortField = sortField, isDescending = isDescending,
                ),
                onQueryChange = { query = it },
                onSort = { field, descending -> sortField = field; isDescending = descending },
                onAction = ::runPageAction,
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
    ) { padding ->
        Box(Modifier.padding(padding).consumeWindowInsets(padding)) {
            Column(Modifier.fillMaxSize()
                .layerBackdrop(contentBackdrop).background(MaterialTheme.colorScheme.background)) {
                if (categoryState.isEnabled) CategoryFilterRow(
                    categoryFilter = categoryFilter,
                    categories = categoryState.categories,
                    onSelect = { categoryFilter = it },
                )
                if (visibleTasks.isEmpty()) {
                    if (!taskState.hasLoaded) Box(Modifier.weight(1f).fillMaxWidth())
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
                                TaskSection(
                                    title = stringResource(if (isCompleted) R.string.task_filter_completed
                                        else R.string.task_unfinished),
                                    count = tasks.size,
                                    isOpen = isOpen,
                                    onClick = {
                                        if (!isSearching) {
                                            if (isCompleted) isCompletedOpen = !isCompletedOpen else isActiveOpen = !isActiveOpen
                                        }
                                    },
                                    onLongClick = {
                                        val ids = tasks.map { it.id }
                                        if (ids.isNotEmpty()) {
                                            if (!selection.isActive) startSelection()
                                            selection.selectAll(ids)
                                        }
                                    },
                                )
                            }
                            if (isOpen) items(tasks, key = { it.id }) { task ->
                                TaskCard(
                                    task = task,
                                    isSelecting = selection.isActive,
                                    isSelected = task.id in selection.selectedIds,
                                    category = categoryState.categories.firstOrNull { it.categoryId == task.categoryId },
                                    isCategoryEnabled = categoryState.isEnabled,
                                    packExtra = PackRegistry[task.packId]?.taskExtra,
                                    onClick = {
                                        if (selection.isActive) selection.toggle(task.id)
                                        else onNavigate(TaskDetailRoute(task.id))
                                    },
                                    onLongClick = {
                                        if (selection.isActive) selection.toggle(task.id)
                                        else startSelection(task.id)
                                    },
                                    onAction = { action ->
                                        when (action) {
                                            TaskAction.STOP -> viewModel.stop(task.id)
                                            TaskAction.PAUSE -> viewModel.pause(task.id)
                                            TaskAction.RESUME -> viewModel.resume(task.id)
                                            TaskAction.FILES -> onNavigate(TaskFilesRoute(task.id))
                                            TaskAction.EDIT -> onNavigate(TaskEditRoute(task.id))
                                            TaskAction.CATEGORY -> categoryTaskIds = listOf(task.id)
                                            TaskAction.OPEN_FILE -> context.openTaskFile(task.outputPath)
                                            TaskAction.OPEN_FOLDER -> context.openFolder(task.outputFolder)
                                            TaskAction.SHARE_FILE -> if (!context.shareTaskFile(task.outputPath)) {
                                                scope.launch {
                                                    snackbarHostState.showSnackbar(context.getString(R.string.task_share_unavailable))
                                                }
                                            }
                                            TaskAction.SHARE_URL -> context.shareText(task.url)
                                            TaskAction.COPY_URL -> {
                                                context.getSystemService(ClipboardManager::class.java)
                                                    .setPrimaryClip(ClipData.newPlainText("url", task.url))
                                                scope.launch { snackbarHostState.showSnackbar(context.getString(R.string.task_detail_copied)) }
                                            }
                                            TaskAction.MOVE_TO_FRONT -> viewModel.moveToFront(listOf(task.id))
                                            TaskAction.VERIFY_HASH -> hashTask = task
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
            AnimatedVisibility(
                visible = selection.isActive,
                modifier = Modifier.align(Alignment.BottomCenter)
                    .padding(bottom = 16.dp + bottomContentPadding),
                enter = slideInVertically { it } + fadeIn(),
                exit = slideOutVertically { it } + fadeOut(),
            ) {
                TaskSelectionBar(
                    targets = targets,
                    isEnabled = taskState.hasLoaded && !isSubmitting,
                    isCategoryEnabled = categoryState.isEnabled,
                    hasSelectableTasks = openSectionIds.isNotEmpty(),
                    onAction = ::runPageAction,
                )
            }
        }
    }

    if (deleteIds.isNotEmpty()) {
        DeleteTasksDialog(
            count = deleteIds.size,
            onDismiss = { deleteIds = emptyList() },
            onConfirm = { shouldDeleteFiles ->
                viewModel.removeEach(deleteIds, shouldDeleteFiles)
                selection.clear()
                deleteIds = emptyList()
            },
        )
    }
    if (categoryTaskIds.isNotEmpty()) {
        val commonCategoryId = allTasks.filter { it.id in categoryTaskIds }
            .map { it.categoryId }.distinct().singleOrNull()
        CategoryPicker(
            title = stringResource(if (categoryTaskIds.size == 1) R.string.task_change_category
                else R.string.task_change_categories, categoryTaskIds.size),
            categories = categoryState.categories,
            selected = commonCategoryId,
            onSelect = { choice ->
                val taskIds = categoryTaskIds
                val categoryId = choice.orEmpty()
                selection.clear()
                scope.launch {
                    val message = try {
                        viewModel.setCategory(taskIds, categoryId)
                        val name = categoryState.categories.firstOrNull { it.categoryId == categoryId }?.name
                            ?: context.getString(R.string.task_uncategorized)
                        context.getString(R.string.task_category_applied, name)
                    } catch (failure: CancellationException) {
                        throw failure
                    } catch (failure: Exception) {
                        context.engineText(failure)
                    }
                    snackbarHostState.showSnackbar(message)
                }
            },
            onDismiss = { categoryTaskIds = emptyList() },
            note = stringResource(R.string.task_category_label_only) +
                if (commonCategoryId == null) "\n" + stringResource(R.string.task_categories_mixed) else "",
        )
    }
    if (redownloadIds.isNotEmpty()) {
        AlertDialog(
            onDismissRequest = { redownloadIds = emptyList() },
            title = { Text(stringResource(R.string.task_detail_redownload)) },
            text = { Text(stringResource(R.string.task_redownload_warning)) },
            confirmButton = { TextButton(onClick = {
                viewModel.redownloadEach(redownloadIds)
                redownloadIds = emptyList()
                selection.clear()
            }) { Text(stringResource(R.string.task_detail_redownload)) } },
            dismissButton = { TextButton(onClick = { redownloadIds = emptyList() }) {
                Text(stringResource(R.string.action_cancel))
            } },
        )
    }
    hashTask?.let { HashSheet(it.id, it.name, onDismiss = { hashTask = null }) }
}

@Composable
private fun TaskSection(
    title: String,
    count: Int,
    isOpen: Boolean,
    onClick: () -> Unit,
    onLongClick: () -> Unit,
) {
    val state = stringResource(if (isOpen) R.string.task_expanded else R.string.task_collapsed)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .semantics { heading(); stateDescription = state }
            .combinedClickable(
                onClick = onClick,
                onLongClick = onLongClick,
                onLongClickLabel = stringResource(R.string.task_select_section),
            )
            .heightIn(min = 48.dp)
            .padding(horizontal = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, style = MaterialTheme.typography.titleSmall)
        Text("  $count", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.weight(1f))
        ExpandChevron(isOpen)
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
