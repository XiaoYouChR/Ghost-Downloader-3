package com.xychr.ghostdownloader.ui.pages
import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.navigation.*
import com.xychr.ghostdownloader.ui.components.draft.*

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DraftPage(
    state: DraftState,
    onUrlsChanged: (String) -> Unit,
    onOpen: (String) -> Unit,
    onRetry: (String) -> Unit,
    onConfirm: () -> Unit,
    onDiscard: () -> Unit,
    onBack: () -> Unit,
    categories: CategoryState,
    onSetCategory: suspend (String, String?) -> Boolean,
    modifier: Modifier = Modifier,
) {
    var isDiscarding by remember { mutableStateOf(false) }
    var categoryUrl by rememberSaveable { mutableStateOf<String?>(null) }
    BackHandler(enabled = state.isWorking) { }
    Scaffold(
        modifier = modifier.sharedContainer(DRAFT_CONTAINER),
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.draft_title)) },
                navigationIcon = { IconButton(onClick = onBack, enabled = !state.isWorking) {
                    Icon(painterResource(R.drawable.ic_arrow_back), stringResource(R.string.action_back))
                } },
                actions = {
                    TextButton(onClick = { isDiscarding = true },
                        enabled = !state.isWorking && (state.urls.isNotBlank() || state.items.isNotEmpty())) {
                        Text(stringResource(R.string.draft_discard))
                    }
                    TextButton(onClick = onConfirm,
                        enabled = state.canConfirm) {
                        Text(stringResource(R.string.draft_start))
                    }
                })
        },
    ) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding).imePadding(),
            contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                OutlinedTextField(value = state.urls, onValueChange = onUrlsChanged,
                    enabled = !state.isWorking, minLines = 3, maxLines = 8,
                    label = { Text(stringResource(R.string.draft_url_hint)) },
                    supportingText = { Text(stringResource(R.string.draft_retained_hint)) },
                    modifier = Modifier.fillMaxWidth())
            }
            if (state.isWorking) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
            state.error?.let { error -> item { Text(error, color = MaterialTheme.colorScheme.error) } }
            if (state.items.any { it.isParsing }) item { Text(stringResource(R.string.draft_deferred_hint)) }
            items(state.items, key = DraftItem::url) { item ->
                DraftCard(item, item.url in state.probing, state.probeErrors[item.url]?.message,
                    onOpen = { if (!state.isWorking) onOpen(item.url) },
                    onRetry = { onRetry(item.url) }, onCategorize = { categoryUrl = item.url },
                    modifier = Modifier.animateItem(), isEnabled = !state.isWorking,
                    category = categories.categories.firstOrNull { it.categoryId == item.categoryId },
                    isCategoryEnabled = categories.isEnabled, isCategoryOpen = categoryUrl == item.url)
            }
        }
    }
    val categoryItem = state.items.firstOrNull { it.url == categoryUrl }
    if (categories.isEnabled && categoryItem != null) key(categoryItem.url) {
        DraftCategorySheet(categoryItem, categories.categories, state.error,
            onApply = { onSetCategory(categoryItem.url, it) }, onDismiss = { categoryUrl = null })
    }
    if (isDiscarding) DiscardDialog(onDismiss = { isDiscarding = false }, onDiscard = {
        isDiscarding = false
        onDiscard()
    })
}

@Composable
internal fun DiscardDialog(onDismiss: () -> Unit, onDiscard: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.draft_discard_question)) },
        confirmButton = { TextButton(onClick = onDiscard) { Text(stringResource(R.string.draft_discard)) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) } })
}
