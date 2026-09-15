package com.xychr.ghostdownloader.ui.components.task

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R

enum class SortField(val labelRes: Int) {
    CREATED(R.string.task_sort_created), COMPLETED(R.string.task_sort_completed),
    NAME(R.string.task_sort_name), SIZE(R.string.task_sort_size), QUEUE(R.string.task_sort_queue),
}

enum class TaskPageAction {
    SEARCH, CLOSE_SEARCH, SELECT, CLOSE_SELECTION, START, PAUSE, DELETE, COPY,
    MOVE_TO_FRONT, REDOWNLOAD, CATEGORIZE, MANAGE_CATEGORIES, SELECT_ALL, INVERT_SELECTION,
}

/** 搜索和选择是两个独立维度——可以一边搜索一边挑选目标，所以不是互斥的 mode 枚举。 */
data class TaskTopBarState(
    val isSelecting: Boolean = false,
    val isSearching: Boolean = false,
    val query: String = "",
    val selectedCount: Int = 0,
    val taskCount: Int = 0,
    val readState: TaskReadState = TaskReadState.LOADING,
    val targets: TaskBatchTargets = TaskBatchTargets(),
    val isSubmitting: Boolean = false,
    val sortField: SortField = SortField.CREATED,
    val isDescending: Boolean = true,
)

/**
 * 内容直接替换，不做 crossfade：动效预算花在容器颜色上（MD3 的多选顶栏就是这么动的）。
 * 这也让搜索框在选择态翻转时保持同一个实例——否则它会重建并重新抢走焦点和键盘。
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun TasksTopBar(
    state: TaskTopBarState,
    onQueryChange: (String) -> Unit,
    onSort: (SortField, Boolean) -> Unit,
    onAction: (TaskPageAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    val containerColor by animateColorAsState(
        targetValue = if (state.isSelecting) MaterialTheme.colorScheme.secondaryContainer
        else MaterialTheme.colorScheme.surface,
        animationSpec = MaterialTheme.motionScheme.fastEffectsSpec(),
        label = "topbar-container",
    )
    TopAppBar(
        modifier = modifier,
        title = {
            when {
                state.isSearching -> TaskSearchField(state.query, onQueryChange)
                state.isSelecting -> Text(
                    text = stringResource(R.string.task_selected_count, state.selectedCount),
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
                else -> Text(stringResource(R.string.nav_tasks))
            }
        },
        expandedHeight = maxOf(64.dp, (32 + 32 * LocalDensity.current.fontScale).dp),
        navigationIcon = {
            // 搜索嵌在选择里：先退出搜索，再退出选择
            if (state.isSearching) TaskIconButton(
                R.drawable.ic_arrow_back, stringResource(R.string.action_back),
            ) { onAction(TaskPageAction.CLOSE_SEARCH) }
            else if (state.isSelecting) TaskIconButton(
                R.drawable.ic_close, stringResource(R.string.action_cancel),
            ) { onAction(TaskPageAction.CLOSE_SELECTION) }
        },
        actions = {
            if (state.isSearching) {
                if (state.query.isNotEmpty()) TaskIconButton(
                    R.drawable.ic_close, stringResource(R.string.action_clear),
                ) { onQueryChange("") }
                if (state.isSelecting) Text(
                    text = stringResource(R.string.task_selected_count, state.selectedCount),
                    style = MaterialTheme.typography.labelLarge,
                    maxLines = 1,
                )
            } else TaskIconButton(
                R.drawable.ic_search, stringResource(R.string.action_search),
            ) { onAction(TaskPageAction.SEARCH) }
            TaskBarMenu(state, onSort, onAction)
        },
        colors = TopAppBarDefaults.topAppBarColors(containerColor = containerColor),
    )
}

@Composable
private fun TaskSearchField(query: String, onQueryChange: (String) -> Unit) {
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    // 只在搜索打开时抢一次焦点；选择态翻转不会重建本实例，所以不会重复触发
    LaunchedEffect(Unit) { focus.requestFocus(); keyboard?.show() }
    TextField(query, onQueryChange, Modifier.fillMaxWidth().focusRequester(focus),
        singleLine = true,
        placeholder = { Text(stringResource(R.string.task_search_hint), maxLines = 1) },
        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
        keyboardActions = KeyboardActions(onSearch = { keyboard?.hide() }),
        colors = TextFieldDefaults.colors(focusedContainerColor = Color.Transparent,
            unfocusedContainerColor = Color.Transparent, disabledContainerColor = Color.Transparent,
            focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent))
}

private enum class MenuLevel { CLOSED, ACTIONS, SORT }

/** 选择态的批量操作在浮动面板上，这里只剩排序——所以选择时直接开排序层，不摆一个单项菜单。 */
@Composable
private fun TaskBarMenu(
    state: TaskTopBarState,
    onSort: (SortField, Boolean) -> Unit,
    onAction: (TaskPageAction) -> Unit,
) {
    var menu by remember { mutableStateOf(MenuLevel.CLOSED) }
    Box {
        TaskIconButton(R.drawable.ic_more_vert, stringResource(R.string.action_more)) {
            menu = if (state.isSelecting) MenuLevel.SORT else MenuLevel.ACTIONS
        }
        DropdownMenu(menu != MenuLevel.CLOSED, onDismissRequest = { menu = MenuLevel.CLOSED }) {
            if (menu == MenuLevel.SORT) {
                if (!state.isSelecting) TaskMenuItem(stringResource(R.string.action_back), R.drawable.ic_arrow_back) {
                    menu = MenuLevel.ACTIONS
                }
                SortField.entries.forEach { field ->
                    DropdownMenuItem(text = { Text(stringResource(field.labelRes)) },
                        leadingIcon = { RadioButton(field == state.sortField, null) },
                        onClick = { onSort(field, state.isDescending); menu = MenuLevel.CLOSED })
                }
                HorizontalDivider()
                listOf(true, false).forEach { descending ->
                    DropdownMenuItem(text = { Text(stringResource(if (descending) R.string.task_sort_descending else R.string.task_sort_ascending)) },
                        leadingIcon = { RadioButton(descending == state.isDescending, null) },
                        onClick = { onSort(state.sortField, descending); menu = MenuLevel.CLOSED })
                }
            } else {
                // 只有常态才会走到这里，所以「所有分类」这个作用域说明是准确的
                val canSubmit = state.readState == TaskReadState.READY && !state.isSubmitting
                val scopeLabel = stringResource(R.string.task_bar_global_scope)
                val startDetail = if (state.targets.retryCount > 0)
                    scopeLabel + "\n" + stringResource(R.string.task_bar_retry_count, state.targets.retryCount)
                else scopeLabel
                TaskMenuItem(stringResource(R.string.task_bar_start_all, state.targets.startIds.size),
                    R.drawable.ic_play, canSubmit && state.targets.startIds.isNotEmpty(), startDetail) {
                    menu = MenuLevel.CLOSED; onAction(TaskPageAction.START)
                }
                TaskMenuItem(stringResource(R.string.task_bar_pause_count, state.targets.pauseIds.size),
                    R.drawable.ic_pause, canSubmit && state.targets.pauseIds.isNotEmpty(),
                    scopeLabel + "\n" + stringResource(R.string.task_bar_pause_skipped, state.targets.skippedPauseCount)) {
                    menu = MenuLevel.CLOSED; onAction(TaskPageAction.PAUSE)
                }
                HorizontalDivider()
                TaskMenuItem(stringResource(R.string.task_select), R.drawable.ic_check, canSubmit && state.taskCount > 0) {
                    menu = MenuLevel.CLOSED; onAction(TaskPageAction.SELECT)
                }
                TaskMenuItem(stringResource(R.string.task_sort), R.drawable.ic_sort) { menu = MenuLevel.SORT }
                TaskMenuItem(stringResource(R.string.category_manage), R.drawable.ic_folder) {
                    menu = MenuLevel.CLOSED; onAction(TaskPageAction.MANAGE_CATEGORIES)
                }
            }
        }
    }
}
