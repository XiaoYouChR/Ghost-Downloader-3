package com.xychr.ghostdownloader.ui.components.draft

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.DraftItem
import com.xychr.ghostdownloader.packs.PackRegistry
import com.xychr.ghostdownloader.ui.util.isValidOutputFolder

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DraftDetailSheet(
    item: DraftItem,
    onOutputFolderChanged: (String) -> Unit,
    sendPack: suspend (String, List<Any?>) -> Unit,
    onDismiss: () -> Unit,
) {
    var folder by rememberSaveable(item.url) { mutableStateOf(item.outputFolder) }
    val trimmed = folder.trim()
    val isValidFolder = isValidOutputFolder(folder)
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                item.name, style = MaterialTheme.typography.titleLarge,
                maxLines = 2, overflow = TextOverflow.Ellipsis,
            )
            OutlinedTextField(
                value = folder, onValueChange = { folder = it },
                label = { Text(stringResource(R.string.task_output_folder)) },
                leadingIcon = { Icon(painterResource(R.drawable.ic_folder), null) },
                singleLine = true,
                isError = !isValidFolder,
                supportingText = if (isValidFolder) null else {
                    { Text(stringResource(R.string.draft_folder_absolute)) }
                },
                modifier = Modifier.fillMaxWidth().onFocusChanged { state ->
                    if (!state.isFocused && isValidFolder && trimmed != item.outputFolder) {
                        onOutputFolderChanged(trimmed)
                    }
                },
            )
            PackRegistry[item.packId]?.draftExtra?.invoke(item.packFields, item.url, sendPack)
        }
    }
}
