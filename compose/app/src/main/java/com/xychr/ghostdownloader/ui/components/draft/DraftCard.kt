package com.xychr.ghostdownloader.ui.components.draft

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.model.Category
import com.xychr.ghostdownloader.model.DraftItem
import com.xychr.ghostdownloader.packs.PackRegistry
import com.xychr.ghostdownloader.ui.components.category.CategoryAction
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes
import com.xychr.ghostdownloader.ui.util.formatSize
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

@Composable
fun DraftCard(
    item: DraftItem,
    onNameChanged: (String) -> Unit,
    onCategorize: () -> Unit,
    onOpenDetail: () -> Unit,
    onOpenFiles: () -> Unit,
    modifier: Modifier = Modifier,
    category: Category? = null,
    isCategoryEnabled: Boolean = false,
    isCategoryOpen: Boolean = false,
    isEnabled: Boolean = true,
) {
    val canInteract = isEnabled && !item.isParsing && item.error == null
    var isEditing by remember { mutableStateOf(false) }
    var editName by rememberSaveable(item.url) { mutableStateOf(item.name) }
    val focusRequester = remember { FocusRequester() }

    val save = {
        val trimmed = editName.trim()
        if (trimmed.isNotBlank() && trimmed != item.name) onNameChanged(trimmed)
        isEditing = false
    }

    LaunchedEffect(isEditing) { if (isEditing) focusRequester.requestFocus() }

    Card(modifier = modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            // Line 1: icon + name + size + overflow
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(painterResource(R.drawable.ic_file), null,
                    Modifier.size(20.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.width(8.dp))
                if (isEditing) {
                    OutlinedTextField(
                        value = editName,
                        onValueChange = { editName = it },
                        singleLine = true,
                        textStyle = MaterialTheme.typography.titleSmall,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = { save() }),
                        modifier = Modifier.weight(1f)
                            .focusRequester(focusRequester)
                            .onFocusChanged { if (!it.isFocused && isEditing) save() },
                    )
                } else {
                    Text(
                        item.name.ifEmpty { item.url },
                        style = MaterialTheme.typography.titleSmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f).clickable(enabled = canInteract) {
                            editName = item.name
                            isEditing = true
                        },
                    )
                }
                if (item.fileSize > 0 && !isEditing) {
                    Spacer(Modifier.width(8.dp))
                    Text(formatSize(item.fileSize), style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                OverflowMenu(item, onOpenDetail, onOpenFiles, canInteract)
            }

            // Line 2: progress / error / summary + category
            when {
                item.isParsing -> LinearProgressIndicator(Modifier.fillMaxWidth())
                item.error != null -> Text(
                    engineText(item.error.message, item.error.params),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
                else -> {
                    val summary = packSummary(item)
                    if (summary != null || (isCategoryEnabled && item.error == null)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            if (summary != null) {
                                Text(summary, style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.clickable(enabled = canInteract, onClick = onOpenDetail))
                            }
                            Spacer(Modifier.weight(1f))
                            if (isCategoryEnabled) {
                                val catName = category?.name ?: stringResource(R.string.task_uncategorized)
                                CategoryAction(
                                    if (item.categoryChoice == null)
                                        stringResource(R.string.draft_category_auto_result, catName)
                                    else catName,
                                    category?.let { categoryIconRes(it.icon) }
                                        ?: if (item.categoryChoice == null) R.drawable.ic_refresh
                                        else R.drawable.ic_file,
                                    onCategorize, isEnabled = isEnabled, isOpen = isCategoryOpen,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun OverflowMenu(
    item: DraftItem,
    onOpenDetail: () -> Unit,
    onOpenFiles: () -> Unit,
    isEnabled: Boolean,
) {
    val hasDetail = PackRegistry[item.packId]?.draftExtra != null
    val hasFiles = item.files.size > 1
    if (!hasDetail && !hasFiles) return

    var isExpanded by remember { mutableStateOf(false) }
    IconButton(onClick = { isExpanded = true }, enabled = isEnabled) {
        Icon(painterResource(R.drawable.ic_more_vert), null)
    }
    DropdownMenu(expanded = isExpanded, onDismissRequest = { isExpanded = false }) {
        if (hasDetail) DropdownMenuItem(
            text = { Text(stringResource(R.string.draft_edit)) },
            onClick = { isExpanded = false; onOpenDetail() },
        )
        if (hasFiles) DropdownMenuItem(
            text = {
                Text(stringResource(R.string.draft_files_selected,
                    item.files.count { it.isSelected }, item.files.size))
            },
            onClick = { isExpanded = false; onOpenFiles() },
        )
    }
}

private fun packSummary(item: DraftItem): String? {
    val pf = item.packFields
    if (pf.isEmpty()) return null
    val parts = buildList {
        val isVideo = pf["isVideoEnabled"]?.jsonPrimitive?.booleanOrNull ?: true
        if (isVideo) {
            val videoTier = pf["videoTier"]?.jsonPrimitive?.contentOrNull.orEmpty()
            if (videoTier.isNotEmpty()) {
                val label = (pf["videoTiers"] as? JsonArray)
                    ?.firstOrNull { it.jsonObject["key"]?.jsonPrimitive?.contentOrNull == videoTier }
                    ?.jsonObject?.get("label")?.jsonPrimitive?.contentOrNull
                add(label ?: videoTier)
            }
        }
        val isAudio = pf["isAudioEnabled"]?.jsonPrimitive?.booleanOrNull ?: true
        if (isAudio) {
            val audioTier = pf["audioTier"]?.jsonPrimitive?.contentOrNull.orEmpty()
            if (audioTier.isNotEmpty()) {
                val label = (pf["audioTiers"] as? JsonArray)
                    ?.firstOrNull { it.jsonObject["key"]?.jsonPrimitive?.contentOrNull == audioTier }
                    ?.jsonObject?.get("label")?.jsonPrimitive?.contentOrNull
                add(label ?: audioTier)
            }
        }
        if (item.files.size > 1) {
            add("${item.files.count { it.isSelected }}/${item.files.size}")
        }
    }
    return parts.joinToString(" · ").ifEmpty { null }
}
