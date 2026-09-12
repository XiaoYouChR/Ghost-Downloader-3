package com.xychr.ghostdownloader.ui.components.task

import com.xychr.ghostdownloader.ui.util.formatSize

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.SizeTransform
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R

enum class SortField(val labelRes: Int) {
    CREATED(R.string.task_sort_created), COMPLETED(R.string.task_sort_completed),
    NAME(R.string.task_sort_name), SIZE(R.string.task_sort_size), QUEUE(R.string.task_sort_queue),
}

enum class TopBarMode { NORMAL, SEARCHING, SELECTING }

enum class TaskPageAction {
    SEARCH, CLOSE_SEARCH, SELECT, CLOSE_SELECTION, START, PAUSE, DELETE, COPY,
    MOVE_TO_FRONT, REDOWNLOAD, CATEGORIZE, MANAGE_CATEGORIES, SELECT_ALL, INVERT_SELECTION,
}

data class TaskTopBarState(
    val mode: TopBarMode = TopBarMode.NORMAL,
    val query: String = "",
    val summary: TaskSummary = TaskSummary(),
    val readState: TaskReadState = TaskReadState.LOADING,
    val targets: TaskBatchTargets = TaskBatchTargets(),
    val taskCount: Int = 0,
    val selectedCount: Int = 0,
    val isCategoryEnabled: Boolean = false,
    val isSubmitting: Boolean = false,
    val sortField: SortField = SortField.CREATED,
    val isDescending: Boolean = true,
)

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun TasksTopBar(
    state: TaskTopBarState,
    onQueryChange: (String) -> Unit,
    onSort: (SortField, Boolean) -> Unit,
    onAction: (TaskPageAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    val effects = MaterialTheme.motionScheme.fastEffectsSpec<Float>()
    val spatial = MaterialTheme.motionScheme.fastSpatialSpec<androidx.compose.ui.unit.IntSize>()
    AnimatedContent(
        targetState = state.mode,
        modifier = modifier,
        transitionSpec = {
            (fadeIn(effects) togetherWith fadeOut(effects)).using(SizeTransform { _, _ -> spatial })
        },
        label = "task-topbar-mode",
    ) { mode ->
        val isCurrent = mode == state.mode
        val canSubmit = isCurrent && state.readState == TaskReadState.READY && !state.isSubmitting
        val isSelecting = mode == TopBarMode.SELECTING
        val startLabel = stringResource(if (isSelecting) R.string.task_bar_start_selected else R.string.task_bar_start_all,
            state.targets.startIds.size)
        val pauseLabel = stringResource(if (isSelecting) R.string.task_bar_pause_selected else R.string.task_bar_pause_count,
            state.targets.pauseIds.size)
        Column(if (isCurrent) Modifier else Modifier.clearAndSetSemantics {}) {
            TopAppBar(
                title = {
                    when (mode) {
                        TopBarMode.NORMAL -> Text(stringResource(R.string.nav_tasks))
                        TopBarMode.SEARCHING -> TaskSearchField(state.query, isCurrent, onQueryChange)
                        TopBarMode.SELECTING -> Text(stringResource(R.string.task_selected_count, state.selectedCount),
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                },
                expandedHeight = maxOf(64.dp, (32 + 32 * LocalDensity.current.fontScale).dp),
                navigationIcon = {
                    if (mode != TopBarMode.NORMAL) TaskBarButton(
                        if (isSelecting) R.drawable.ic_close else R.drawable.ic_arrow_back,
                        stringResource(if (isSelecting) R.string.action_cancel else R.string.action_back),
                        isCurrent,
                    ) { onAction(if (isSelecting) TaskPageAction.CLOSE_SELECTION else TaskPageAction.CLOSE_SEARCH) }
                },
                actions = {
                    when (mode) {
                        TopBarMode.NORMAL -> TaskBarButton(R.drawable.ic_search,
                            stringResource(R.string.action_search), isCurrent) { onAction(TaskPageAction.SEARCH) }
                        TopBarMode.SEARCHING -> if (state.query.isNotEmpty()) TaskBarButton(R.drawable.ic_close,
                            stringResource(R.string.action_clear), isCurrent) { onQueryChange("") }
                        TopBarMode.SELECTING -> {
                            TaskBarButton(R.drawable.ic_play, startLabel, canSubmit && state.targets.startIds.isNotEmpty()) {
                                onAction(TaskPageAction.START)
                            }
                            TaskBarButton(R.drawable.ic_pause, pauseLabel, canSubmit && state.targets.pauseIds.isNotEmpty()) {
                                onAction(TaskPageAction.PAUSE)
                            }
                        }
                    }
                    if (mode != TopBarMode.SEARCHING) TaskBarMenu(state, isSelecting, isCurrent,
                        startLabel, pauseLabel, onSort, onAction)
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = if (isSelecting)
                    MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface),
            )
            if (!isSelecting) TaskSpeedSummary(state.summary, state.readState, mode == TopBarMode.SEARCHING)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun TaskSpeedSummary(summary: TaskSummary, readState: TaskReadState, isCompact: Boolean) {
    val effects = MaterialTheme.motionScheme.fastEffectsSpec<Float>()
    val spatial = MaterialTheme.motionScheme.fastSpatialSpec<androidx.compose.ui.unit.IntSize>()
    val hasActivity = summary.running + summary.waiting > 0
    Surface(color = MaterialTheme.colorScheme.surface) {
        AnimatedContent(
            targetState = readState to hasActivity,
            contentKey = { (read, active) -> if (read == TaskReadState.READY) read to active else read to false },
            transitionSpec = {
                (fadeIn(effects) togetherWith fadeOut(effects)).using(SizeTransform { _, _ -> spatial })
            }, label = "task-summary-state",
        ) { (read, active) ->
            FlowRow(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, bottom = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (read == TaskReadState.READY && active) {
                    val speed = stringResource(R.string.task_bar_speed, formatSize(summary.speed))
                    Row(Modifier.semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically) {
                        Icon(painterResource(R.drawable.ic_download), null, Modifier.size(18.dp),
                            tint = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.width(4.dp))
                        Text(speed, style = MaterialTheme.typography.labelLarge.copy(fontFeatureSettings = "tnum"),
                            color = MaterialTheme.colorScheme.primary)
                    }
                    if (!isCompact) Text(stringResource(R.string.task_bar_counts, summary.running, summary.waiting),
                        style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    Text(stringResource(when (read) {
                        TaskReadState.LOADING -> R.string.task_bar_loading
                        TaskReadState.UNAVAILABLE -> R.string.task_bar_unavailable
                        TaskReadState.READY -> R.string.task_bar_idle
                    }), style = MaterialTheme.typography.labelLarge,
                        color = if (read == TaskReadState.UNAVAILABLE) MaterialTheme.colorScheme.error
                            else MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun TaskSearchField(query: String, isActive: Boolean, onQueryChange: (String) -> Unit) {
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    LaunchedEffect(isActive) {
        if (isActive) { focus.requestFocus(); keyboard?.show() }
    }
    TextField(query, onQueryChange, Modifier.fillMaxWidth().focusRequester(focus),
        enabled = isActive, singleLine = true,
        placeholder = { Text(stringResource(R.string.task_search_hint), maxLines = 1) },
        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
        keyboardActions = KeyboardActions(onSearch = { keyboard?.hide() }),
        colors = TextFieldDefaults.colors(focusedContainerColor = Color.Transparent,
            unfocusedContainerColor = Color.Transparent, disabledContainerColor = Color.Transparent,
            focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent))
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TaskBarButton(icon: Int, label: String, isEnabled: Boolean, onClick: () -> Unit) {
    TooltipBox(positionProvider = TooltipDefaults.rememberTooltipPositionProvider(TooltipAnchorPosition.Above),
        tooltip = { PlainTooltip { Text(label) } }, state = rememberTooltipState()) {
        IconButton(onClick, enabled = isEnabled, modifier = Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp)) {
            Icon(painterResource(icon), label)
        }
    }
}

private enum class TaskMenu { CLOSED, ACTIONS, SORT }

@Composable
private fun TaskBarMenu(
    state: TaskTopBarState, isSelecting: Boolean, isCurrent: Boolean, startLabel: String, pauseLabel: String,
    onSort: (SortField, Boolean) -> Unit, onAction: (TaskPageAction) -> Unit,
) {
    var menu by remember { mutableStateOf(TaskMenu.CLOSED) }
    LaunchedEffect(isCurrent) { if (!isCurrent) menu = TaskMenu.CLOSED }
    val canSubmit = isCurrent && state.readState == TaskReadState.READY && !state.isSubmitting
    val hasSelection = canSubmit && state.selectedCount > 0
    val scopeLabel = stringResource(if (isSelecting) R.string.task_bar_selected_scope else R.string.task_bar_global_scope)
    val startDetail = if (state.targets.retryCount > 0)
        scopeLabel + "\n" + stringResource(R.string.task_bar_retry_count, state.targets.retryCount) else scopeLabel
    Box {
        TaskBarButton(R.drawable.ic_more_vert, stringResource(R.string.action_more), isCurrent) { menu = TaskMenu.ACTIONS }
        DropdownMenu(menu != TaskMenu.CLOSED && isCurrent, onDismissRequest = { menu = TaskMenu.CLOSED }) {
            if (menu == TaskMenu.SORT) {
                TaskBarMenuItem(stringResource(R.string.action_back), R.drawable.ic_arrow_back) { menu = TaskMenu.ACTIONS }
                SortField.entries.forEach { field ->
                    DropdownMenuItem(text = { Text(stringResource(field.labelRes)) },
                        leadingIcon = { RadioButton(field == state.sortField, null) },
                        onClick = { onSort(field, state.isDescending); menu = TaskMenu.CLOSED })
                }
                HorizontalDivider()
                listOf(true, false).forEach { descending ->
                    DropdownMenuItem(text = { Text(stringResource(if (descending) R.string.task_sort_descending else R.string.task_sort_ascending)) },
                        leadingIcon = { RadioButton(descending == state.isDescending, null) },
                        onClick = { onSort(state.sortField, descending); menu = TaskMenu.CLOSED })
                }
            } else {
                TaskBarMenuItem(startLabel, R.drawable.ic_play, canSubmit && state.targets.startIds.isNotEmpty(),
                    startDetail) {
                    menu = TaskMenu.CLOSED; onAction(TaskPageAction.START)
                }
                TaskBarMenuItem(pauseLabel, R.drawable.ic_pause, canSubmit && state.targets.pauseIds.isNotEmpty(),
                    scopeLabel + "\n" + stringResource(R.string.task_bar_pause_skipped, state.targets.skippedPauseCount)) {
                    menu = TaskMenu.CLOSED; onAction(TaskPageAction.PAUSE)
                }
                HorizontalDivider()
                if (isSelecting) {
                    TaskBarMenuItem(stringResource(R.string.action_delete), R.drawable.ic_delete, hasSelection) {
                        menu = TaskMenu.CLOSED; onAction(TaskPageAction.DELETE)
                    }
                    TaskBarMenuItem(stringResource(R.string.task_detail_copy_url), R.drawable.ic_copy, hasSelection) {
                        menu = TaskMenu.CLOSED; onAction(TaskPageAction.COPY)
                    }
                    TaskBarMenuItem(stringResource(R.string.task_detail_move_to_front), R.drawable.ic_arrow_upward, hasSelection) {
                        menu = TaskMenu.CLOSED; onAction(TaskPageAction.MOVE_TO_FRONT)
                    }
                    TaskBarMenuItem(stringResource(R.string.task_detail_redownload), R.drawable.ic_refresh, hasSelection) {
                        menu = TaskMenu.CLOSED; onAction(TaskPageAction.REDOWNLOAD)
                    }
                    if (state.isCategoryEnabled) TaskBarMenuItem(stringResource(R.string.task_change_category), R.drawable.ic_folder, hasSelection) {
                        menu = TaskMenu.CLOSED; onAction(TaskPageAction.CATEGORIZE)
                    }
                    HorizontalDivider()
                    TaskBarMenuItem(stringResource(R.string.task_select_all), R.drawable.ic_check, canSubmit && state.taskCount > 0) {
                        menu = TaskMenu.CLOSED; onAction(TaskPageAction.SELECT_ALL)
                    }
                    TaskBarMenuItem(stringResource(R.string.task_select_invert), R.drawable.ic_restore, canSubmit && state.taskCount > 0) {
                        menu = TaskMenu.CLOSED; onAction(TaskPageAction.INVERT_SELECTION)
                    }
                } else {
                    TaskBarMenuItem(stringResource(R.string.task_select), R.drawable.ic_check, canSubmit && state.taskCount > 0) {
                        menu = TaskMenu.CLOSED; onAction(TaskPageAction.SELECT)
                    }
                    TaskBarMenuItem(stringResource(R.string.task_sort), R.drawable.ic_sort) { menu = TaskMenu.SORT }
                    TaskBarMenuItem(stringResource(R.string.category_manage), R.drawable.ic_folder) {
                        menu = TaskMenu.CLOSED; onAction(TaskPageAction.MANAGE_CATEGORIES)
                    }
                }
            }
        }
    }
}

@Composable
private fun TaskBarMenuItem(label: String, icon: Int, isEnabled: Boolean = true, detail: String? = null, onClick: () -> Unit) {
    DropdownMenuItem(text = {
        Column {
            Text(label)
            if (detail != null) Text(detail, style = MaterialTheme.typography.bodySmall)
        }
    }, leadingIcon = { Icon(painterResource(icon), null) }, enabled = isEnabled, onClick = onClick)
}
