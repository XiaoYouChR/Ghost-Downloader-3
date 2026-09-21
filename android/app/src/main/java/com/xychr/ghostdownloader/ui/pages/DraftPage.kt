package com.xychr.ghostdownloader.ui.pages

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.SettingRanges
import com.xychr.ghostdownloader.ui.components.ErrorText
import com.xychr.ghostdownloader.ui.components.RenameDialog
import com.xychr.ghostdownloader.ui.components.settings.PathSettingRow
import com.xychr.ghostdownloader.ui.platform.rememberFolderPicker
import com.xychr.ghostdownloader.model.CategoryState
import com.xychr.ghostdownloader.model.DraftItem
import kotlin.math.roundToInt
import com.xychr.ghostdownloader.ui.components.category.CategoryPicker
import com.xychr.ghostdownloader.ui.components.draft.DiscardDialog
import com.xychr.ghostdownloader.ui.components.draft.DraftCard
import com.xychr.ghostdownloader.ui.components.draft.DraftState
import com.xychr.ghostdownloader.ui.components.draft.DraftViewModel
import com.xychr.ghostdownloader.ui.components.draft.FileSelectSheet
import com.xychr.ghostdownloader.ui.navigation.DRAFT_CONTAINER
import com.xychr.ghostdownloader.ui.navigation.sharedContainer
import com.xychr.ghostdownloader.ui.util.formatSize
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DraftPage(
    state: DraftState,
    draft: DraftViewModel,
    onConfirm: (autoStart: Boolean) -> Unit,
    onDiscard: () -> Unit,
    onBack: () -> Unit,
    onOpenEdit: (String) -> Unit,
    categories: CategoryState,
    modifier: Modifier = Modifier,
) {
    var isDiscarding by remember { mutableStateOf(false) }
    var categoryUrl by rememberSaveable { mutableStateOf<String?>(null) }
    var renameUrl by rememberSaveable { mutableStateOf<String?>(null) }
    var filesUrl by rememberSaveable { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val folderPicker = rememberFolderPicker(draft::setGlobalFolder)

    BackHandler(enabled = state.isWorking) { }

    Scaffold(
        modifier = modifier.sharedContainer(DRAFT_CONTAINER),
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.draft_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack, enabled = !state.isWorking) {
                        Icon(painterResource(R.drawable.ic_arrow_back), stringResource(R.string.action_back))
                    }
                },
                actions = {
                    IconButton(
                        onClick = { isDiscarding = true },
                        enabled = !state.isWorking && (state.urls.isNotBlank() || state.items.isNotEmpty()),
                    ) {
                        Icon(painterResource(R.drawable.ic_delete), stringResource(R.string.draft_discard))
                    }
                    IconButton(onClick = { onConfirm(false) }, enabled = state.canConfirm) {
                        Icon(painterResource(R.drawable.ic_restore), stringResource(R.string.draft_later))
                    }
                    FilledIconButton(onClick = { onConfirm(true) }, enabled = state.canConfirm) {
                        Icon(painterResource(R.drawable.ic_play), stringResource(R.string.draft_start))
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding).imePadding(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                OutlinedTextField(
                    value = state.urls,
                    onValueChange = draft::setUrls,
                    enabled = !state.isWorking,
                    minLines = 3, maxLines = 8,
                    label = { Text(stringResource(R.string.draft_url_hint)) },
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            if (state.isWorking) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }

            state.error?.let { error ->
                item { ErrorText(error) }
            }

            if (state.items.size > 1) stickyHeader { DraftGroupHeader(state) }

            items(state.items, key = DraftItem::url) { item ->
                DraftCard(
                    item = item,
                    onRename = { renameUrl = item.url },
                    onOpenOptions = { onOpenEdit(item.url) },
                    onCategorize = { categoryUrl = item.url },
                    onRefresh = { scope.launch { draft.refresh(item.url) } },
                    onSelectFiles = { filesUrl = item.url },
                    onSelectControl = { id, value -> scope.launch { draft.setControl(item.url, id, value) } },
                    modifier = Modifier.animateItem(),
                    category = categories.categories.firstOrNull { it.categoryId == item.categoryId },
                    isCategoryEnabled = categories.isEnabled,
                    isEnabled = !state.isWorking,
                )
            }

            if (state.items.any { it.error == null && !it.isParsing }) {
                item {
                    PathSettingRow(
                        title = stringResource(R.string.task_output_folder),
                        path = state.globalFolder,
                        picker = folderPicker,
                        isEnabled = !state.isWorking,
                        error = if (state.isFolderValid) null
                        else stringResource(R.string.draft_folder_absolute),
                    )
                }
                if (state.subworkerCount > 0) {
                    item {
                        val range = remember { SettingRanges["preBlockNum"] }
                        val span = range.last - range.first
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                stringResource(R.string.settings_pre_block_num),
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier.weight(1f),
                            )
                            Text(
                                state.subworkerCount.toString(),
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Slider(
                            value = state.subworkerCount.toFloat(),
                            onValueChange = { draft.setSubworkerCount(it.roundToInt()) },
                            valueRange = range.first.toFloat()..range.last.toFloat(),
                            steps = if (span <= 20) span - 1 else 0,
                            enabled = !state.isWorking,
                        )
                    }
                }
            }
        }
    }

    val categoryItem = state.items.firstOrNull { it.url == categoryUrl }
    if (categories.isEnabled && categoryItem != null) CategoryPicker(
        title = stringResource(R.string.task_change_category),
        categories = categories.categories,
        selected = categoryItem.categoryChoice,
        onSelect = { choice -> scope.launch { draft.setCategory(categoryItem.url, choice) } },
        onDismiss = { categoryUrl = null },
        hasAuto = true,
        note = listOfNotNull(
            categoryItem.name,
            stringResource(R.string.draft_category_multiple).takeIf { categoryItem.files.size > 1 },
        ).joinToString("\n"),
    )

    val renameItem = state.items.firstOrNull { it.url == renameUrl }
    if (renameItem != null) RenameDialog(
        current = renameItem.name,
        onDismiss = { renameUrl = null },
        onConfirm = { draft.setName(renameItem.url, it) },
    )

    val filesItem = state.items.firstOrNull { it.url == filesUrl }
    if (filesItem != null) FileSelectSheet(
        files = filesItem.files,
        canRename = filesItem.canRenameFiles,
        onApply = { draft.updateFiles(filesItem.url, filesItem.files, it) },
        onDismiss = { filesUrl = null },
    )

    if (isDiscarding) DiscardDialog(
        onDismiss = { isDiscarding = false },
        onDiscard = { isDiscarding = false; onDiscard() },
    )
}

@Composable
private fun DraftGroupHeader(state: DraftState) {
    val failures = state.items.count { it.error != null }
    val size = state.items.sumOf { it.fileSize }
    Row(
        Modifier.fillMaxWidth()
            .background(MaterialTheme.colorScheme.background)
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(stringResource(R.string.draft_count, state.items.size),
            style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.weight(1f))
        if (failures > 0) Text(
            stringResource(R.string.draft_parse_failed, failures),
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.error,
        )
        if (size > 0) {
            if (failures > 0) Spacer(Modifier.width(8.dp))
            Text(formatSize(size),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
