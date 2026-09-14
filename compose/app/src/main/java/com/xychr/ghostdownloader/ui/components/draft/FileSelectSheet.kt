package com.xychr.ghostdownloader.ui.components.draft

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
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
import com.xychr.ghostdownloader.model.DraftFile

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FileSelectSheet(
    files: List<DraftFile>,
    canRename: Boolean,
    onApply: (List<DraftFile>) -> Unit,
    onDismiss: () -> Unit,
) {
    var editedFiles by remember { mutableStateOf(files) }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxHeight(0.85f)) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    stringResource(R.string.draft_select_files),
                    style = MaterialTheme.typography.titleLarge,
                )
                Spacer(Modifier.weight(1f))
                Text(
                    stringResource(R.string.draft_files_selected, editedFiles.count { it.isSelected }, editedFiles.size),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            FileSelect(editedFiles, canRename, onChange = { editedFiles = it }, modifier = Modifier.weight(1f))
            Button(
                onClick = { onApply(editedFiles); onDismiss() },
                modifier = Modifier.fillMaxWidth().padding(16.dp),
            ) {
                Text(stringResource(R.string.draft_apply))
            }
        }
    }
}
