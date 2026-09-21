package com.xychr.ghostdownloader.ui.pages

import androidx.compose.foundation.clickable
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.model.DraftItem
import com.xychr.ghostdownloader.model.TaskEditResult
import com.xychr.ghostdownloader.packs.PackRegistry
import com.xychr.ghostdownloader.ui.components.draft.DraftViewModel
import com.xychr.ghostdownloader.ui.components.draft.FileSelectSheet

@Composable
fun DraftEditPage(item: DraftItem, draft: DraftViewModel, onBack: () -> Unit) {
    val url = item.url
    val model: TaskEditViewModel = viewModel(key = url) {
        TaskEditViewModel(
            fetch = { engineRepository.query("draftOptions", url) },
            send = { options, _ ->
                engineRepository.invoke("applyDraftEdit", url, engineRepository.encode(options))
                TaskEditResult()
            },
        )
    }
    val state by model.state.collectAsStateWithLifecycle()
    var isSelectingFiles by rememberSaveable(url) { mutableStateOf(false) }

    LaunchedEffect(state.isDone) { if (state.isDone) onBack() }

    TaskOptionsEditor(state, model::update, { model.save() }, onBack,
        onRetry = model::refresh,
        saveLabel = R.string.draft_apply,
    ) {
        if (item.files.size > 1) FilesRow(
            count = item.files.count { it.isSelected },
            total = item.files.size,
            isEnabled = !state.isSaving,
            onOpen = { isSelectingFiles = true },
        )
        PackRegistry[item.packId]?.draftExtra?.invoke(item.packFields, item.url) { action, args ->
            draft.sendPack(item.url, action, args)
        }
    }

    if (isSelectingFiles) FileSelectSheet(
        files = item.files,
        canRename = item.canRenameFiles,
        onApply = { draft.updateFiles(item.url, item.files, it) },
        onDismiss = { isSelectingFiles = false },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilesRow(count: Int, total: Int, isEnabled: Boolean, onOpen: () -> Unit) {
    ListItem(
        supportingContent = { Text(stringResource(R.string.draft_files_selected, count, total)) },
        trailingContent = {
            Icon(painterResource(R.drawable.ic_chevron_right), null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant)
        },
        modifier = Modifier.clickable(enabled = isEnabled, onClick = onOpen),
    ) { Text(stringResource(R.string.draft_select_files)) }
}
