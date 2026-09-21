package com.xychr.ghostdownloader.ui.components.task

import androidx.compose.foundation.layout.Box
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R

@Composable
fun TaskMenu(menu: List<TaskActionSpec>, onAction: (TaskAction) -> Unit) {
    var isOpen by remember { mutableStateOf(false) }
    Box {
        TaskIconButton(R.drawable.ic_more_vert, stringResource(R.string.action_more)) { isOpen = true }
        DropdownMenu(expanded = isOpen, onDismissRequest = { isOpen = false }) {
            for (spec in menu) {
                if (spec.action == TaskAction.DELETE) HorizontalDivider()
                TaskMenuItem(stringResource(spec.label), spec.icon, spec.isEnabled) {
                    isOpen = false
                    onAction(spec.action)
                }
            }
        }
    }
}
