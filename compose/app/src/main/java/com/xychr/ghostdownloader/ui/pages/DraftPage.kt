package com.xychr.ghostdownloader.ui.pages

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.CategoryState
import com.xychr.ghostdownloader.model.DraftItem
import com.xychr.ghostdownloader.ui.components.category.CategoryPicker
import com.xychr.ghostdownloader.ui.components.draft.DiscardDialog
import com.xychr.ghostdownloader.ui.components.draft.DraftCard
import com.xychr.ghostdownloader.ui.components.draft.DraftDetailSheet
import com.xychr.ghostdownloader.ui.components.draft.DraftState
import com.xychr.ghostdownloader.ui.components.draft.DraftViewModel
import com.xychr.ghostdownloader.ui.components.draft.FileSelectSheet
import com.xychr.ghostdownloader.ui.navigation.DRAFT_CONTAINER
import com.xychr.ghostdownloader.ui.navigation.sharedContainer
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DraftPage(
    state: DraftState,
    draft: DraftViewModel,
    onConfirm: (autoStart: Boolean) -> Unit,
    onDiscard: () -> Unit,
    onBack: () -> Unit,
    categories: CategoryState,
    modifier: Modifier = Modifier,
) {
    var isDiscarding by remember { mutableStateOf(false) }
    var categoryUrl by rememberSaveable { mutableStateOf<String?>(null) }
    var detailUrl by rememberSaveable { mutableStateOf<String?>(null) }
    var filesUrl by rememberSaveable { mutableStateOf<String?>(null) }
    var globalFolder by rememberSaveable { mutableStateOf("") }
    val scope = rememberCoroutineScope()

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
                item { Text(error, color = MaterialTheme.colorScheme.error) }
            }

            items(state.items, key = DraftItem::url) { item ->
                DraftCard(
                    item = item,
                    onNameChanged = { draft.setName(item.url, it) },
                    onCategorize = { categoryUrl = item.url },
                    onOpenDetail = { detailUrl = item.url },
                    onOpenFiles = { filesUrl = item.url },
                    modifier = Modifier.animateItem(),
                    category = categories.categories.firstOrNull { it.categoryId == item.categoryId },
                    isCategoryEnabled = categories.isEnabled,
                    isCategoryOpen = categoryUrl == item.url,
                    isEnabled = !state.isWorking,
                )
            }

            if (state.items.any { it.error == null && !it.isParsing }) {
                item {
                    ListItem(
                        leadingContent = {
                            Icon(painterResource(R.drawable.ic_folder), null,
                                tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        },
                        headlineContent = {
                            val folder = globalFolder.ifEmpty {
                                state.items.firstOrNull { it.error == null && !it.isParsing }
                                    ?.outputFolder.orEmpty()
                            }
                            OutlinedTextField(
                                value = folder,
                                onValueChange = { globalFolder = it },
                                singleLine = true,
                                label = { Text(stringResource(R.string.task_output_folder)) },
                                modifier = Modifier.fillMaxWidth(),
                            )
                        },
                        trailingContent = {
                            IconButton(
                                onClick = { draft.setGlobalOutputFolder(globalFolder.trim()) },
                                enabled = globalFolder.isNotBlank(),
                            ) {
                                Icon(painterResource(R.drawable.ic_check), stringResource(R.string.draft_apply))
                            }
                        },
                    )
                }
            }
        }
    }

    // Category picker sheet
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

    // Detail sheet
    val detailItem = state.items.firstOrNull { it.url == detailUrl }
    if (detailItem != null) DraftDetailSheet(
        item = detailItem,
        onOutputFolderChanged = { draft.setOutputFolder(detailItem.url, it) },
        sendPack = { action, args -> draft.sendPack(detailItem.url, action, args) },
        onDismiss = { detailUrl = null },
    )

    // File select sheet
    val filesItem = state.items.firstOrNull { it.url == filesUrl }
    if (filesItem != null) FileSelectSheet(
        files = filesItem.files,
        canRename = filesItem.canRenameFiles,
        onApply = { draft.applyFiles(filesItem.url, filesItem.files, it) },
        onDismiss = { filesUrl = null },
    )

    // Discard confirmation
    if (isDiscarding) DiscardDialog(
        onDismiss = { isDiscarding = false },
        onDiscard = { isDiscarding = false; onDiscard() },
    )
}
