package com.xychr.ghostdownloader.ui.components.task

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R

@Composable
fun TaskSelectionBar(
    targets: TaskBatchTargets,
    isEnabled: Boolean,
    isCategoryEnabled: Boolean,
    hasSelectableTasks: Boolean,
    onAction: (TaskPageAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = MaterialTheme.shapes.extraLarge,
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
        shadowElevation = 6.dp,
    ) {
        Row(Modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            if (targets.startIds.isNotEmpty()) TaskIconButton(
                R.drawable.ic_play,
                stringResource(R.string.task_bar_start_selected, targets.startIds.size),
                isEnabled,
            ) { onAction(TaskPageAction.START) }
            if (targets.pauseIds.isNotEmpty()) TaskIconButton(
                R.drawable.ic_pause,
                stringResource(R.string.task_bar_pause_selected, targets.pauseIds.size),
                isEnabled,
            ) { onAction(TaskPageAction.PAUSE) }
            TaskIconButton(R.drawable.ic_delete, stringResource(R.string.action_delete), isEnabled) {
                onAction(TaskPageAction.DELETE)
            }
            TaskSelectionMenu(isEnabled, isCategoryEnabled, hasSelectableTasks, onAction)
        }
    }
}

@Composable
private fun TaskSelectionMenu(
    isEnabled: Boolean,
    isCategoryEnabled: Boolean,
    hasSelectableTasks: Boolean,
    onAction: (TaskPageAction) -> Unit,
) {
    var isOpen by remember { mutableStateOf(false) }
    Box {
        // 菜单入口本身不受 isEnabled 约束：提交进行中仍要能调整选择
        TaskIconButton(R.drawable.ic_more_vert, stringResource(R.string.action_more)) { isOpen = true }
        DropdownMenu(expanded = isOpen, onDismissRequest = { isOpen = false }) {
            TaskMenuItem(stringResource(R.string.task_detail_copy_url), R.drawable.ic_copy, isEnabled) {
                isOpen = false; onAction(TaskPageAction.COPY)
            }
            TaskMenuItem(stringResource(R.string.task_detail_move_to_front), R.drawable.ic_arrow_upward, isEnabled) {
                isOpen = false; onAction(TaskPageAction.MOVE_TO_FRONT)
            }
            TaskMenuItem(stringResource(R.string.task_detail_redownload), R.drawable.ic_restore, isEnabled) {
                isOpen = false; onAction(TaskPageAction.REDOWNLOAD)
            }
            if (isCategoryEnabled) TaskMenuItem(
                stringResource(R.string.task_change_category), R.drawable.ic_folder, isEnabled,
            ) { isOpen = false; onAction(TaskPageAction.CATEGORIZE) }
            HorizontalDivider()
            // 全选／反选改的是选择本身，不下发请求，所以只看有没有可选项
            TaskMenuItem(stringResource(R.string.task_select_all), R.drawable.ic_check, hasSelectableTasks) {
                isOpen = false; onAction(TaskPageAction.SELECT_ALL)
            }
            TaskMenuItem(stringResource(R.string.task_select_missing), R.drawable.ic_folder_off, hasSelectableTasks) {
                isOpen = false; onAction(TaskPageAction.SELECT_MISSING)
            }
            TaskMenuItem(stringResource(R.string.task_select_invert), R.drawable.ic_restore, hasSelectableTasks) {
                isOpen = false; onAction(TaskPageAction.INVERT_SELECTION)
            }
        }
    }
}
