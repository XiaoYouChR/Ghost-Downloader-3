package com.xychr.ghostdownloader.ui.components.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.platform.FolderPickerState
import com.xychr.ghostdownloader.ui.platform.loadRecentFolders
import com.xychr.ghostdownloader.ui.platform.saveRecentFolder

@Composable
fun PathSettingRow(
    title: String,
    path: String,
    picker: FolderPickerState,
    subtitle: String? = null,
    isEnabled: Boolean = true,
    error: String? = null,
    onReset: (() -> Unit)? = null,
) {
    val context = LocalContext.current
    var recents by remember { mutableStateOf<List<String>>(emptyList()) }
    var isChoosing by remember { mutableStateOf(false) }

    val choose: () -> Unit = {
        isChoosing = false
        picker.launch()
    }
    val pick: (String) -> Unit = { folder ->
        isChoosing = false
        saveRecentFolder(context, folder)
        picker.onPicked(folder)
    }

    Column {
        ActionSettingRow(
            title = title,
            subtitle = subtitle ?: path,
            onClick = {
                if (!isEnabled) return@ActionSettingRow
                val history = loadRecentFolders(context)
                if (history.isEmpty()) choose() else {
                    recents = history
                    isChoosing = true
                }
            },
            trailing = onReset?.let { reset ->
                {
                    IconButton(onClick = reset, enabled = isEnabled) {
                        Icon(
                            painterResource(R.drawable.ic_restore),
                            contentDescription = stringResource(R.string.settings_restore_default),
                        )
                    }
                }
            },
        )
        val note = if (picker.isRejected) stringResource(R.string.task_local_folder_only) else error
        if (note != null) Text(
            note,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.error,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
        )
    }

    if (isChoosing) AlertDialog(
        onDismissRequest = { isChoosing = false },
        title = { Text(title) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()).selectableGroup()) {
                recents.forEach { folder ->
                    RadioRow(folder, folder == path) { pick(folder) }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = choose) { Text(stringResource(R.string.path_choose_folder)) }
        },
        dismissButton = {
            TextButton(onClick = { isChoosing = false }) {
                Text(stringResource(R.string.action_cancel))
            }
        },
    )
}
