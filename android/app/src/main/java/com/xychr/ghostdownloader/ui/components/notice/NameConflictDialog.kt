package com.xychr.ghostdownloader.ui.components.notice

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.NameConflict
import com.xychr.ghostdownloader.ui.util.formatSize
import com.xychr.ghostdownloader.ui.util.formatTimestamp

@Composable
fun NameConflictDialog(
    conflict: NameConflict,
    onChoice: (choice: String, isAppliedToRest: Boolean) -> Unit,
) {
    var isAppliedToRest by remember(conflict.taskId) { mutableStateOf(false) }
    val modified = formatTimestamp(conflict.modifiedAt)
    AlertDialog(
        onDismissRequest = { onChoice("", false) },
        title = { Text(stringResource(R.string.name_conflict_title, conflict.name)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    if (conflict.isFolder) stringResource(R.string.name_conflict_existing_folder, modified)
                    else stringResource(R.string.name_conflict_existing_file, formatSize(conflict.existingSize), modified),
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(
                    stringResource(
                        R.string.name_conflict_new_file,
                        if (conflict.newSize > 0) formatSize(conflict.newSize) else stringResource(R.string.name_conflict_unknown_size),
                    ),
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(stringResource(R.string.name_conflict_overwrite_hint), style = MaterialTheme.typography.bodyMedium)
                if (conflict.restCount > 0) {
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = 48.dp)
                            .toggleable(isAppliedToRest, role = Role.Checkbox, onValueChange = { isAppliedToRest = it }),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Checkbox(isAppliedToRest, onCheckedChange = null)
                        Text(
                            stringResource(R.string.name_conflict_apply_to_rest, conflict.restCount),
                            Modifier.padding(start = 12.dp),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
            }
        },
        confirmButton = {
            Row {
                TextButton({ onChoice("overwrite", isAppliedToRest) }) {
                    Text(stringResource(R.string.name_conflict_overwrite))
                }
                TextButton({ onChoice("keepBoth", isAppliedToRest) }) {
                    Text(stringResource(R.string.name_conflict_keep_both))
                }
            }
        },
        dismissButton = { TextButton({ onChoice("", false) }) { Text(stringResource(R.string.action_cancel)) } },
    )
}
