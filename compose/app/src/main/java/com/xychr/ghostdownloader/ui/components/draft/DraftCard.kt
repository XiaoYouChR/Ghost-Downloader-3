package com.xychr.ghostdownloader.ui.components.draft

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.IconButton
import androidx.compose.material3.Icon
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
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes
import com.xychr.ghostdownloader.ui.util.formatSize

@OptIn(ExperimentalLayoutApi::class)
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
    isEnabled: Boolean = true,
) {
    val canInteract = isEnabled && !item.isParsing && item.error == null
    var isEditing by rememberSaveable(item.url) { mutableStateOf(false) }
    var editName by rememberSaveable(item.url) { mutableStateOf(item.name) }
    val focusRequester = remember { FocusRequester() }

    val save = {
        val trimmed = editName.trim()
        if (trimmed.isNotBlank() && trimmed != item.name) onNameChanged(trimmed)
        isEditing = false
    }

    LaunchedEffect(isEditing) { if (isEditing) focusRequester.requestFocus() }

    Card(modifier = modifier.fillMaxWidth().animateContentSize()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
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
                        modifier = Modifier.weight(1f)
                            .heightIn(min = 48.dp)
                            .clickable(
                                enabled = canInteract,
                                onClickLabel = stringResource(R.string.file_rename),
                            ) {
                                editName = item.name
                                isEditing = true
                            }
                            .wrapContentHeight(),
                    )
                }
                if (item.fileSize > 0 && !isEditing) {
                    Spacer(Modifier.width(8.dp))
                    Text(formatSize(item.fileSize), style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }

            when {
                item.isParsing -> LinearProgressIndicator(Modifier.fillMaxWidth())
                item.error != null -> Text(
                    engineText(item.error),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
                else -> {
                    // 入口按"这个 pack 有没有详情页"开，不按概要开——否则用户关掉所有轨道后
                    // 概要变 null，chip 消失，就再也进不去把轨道开回来了
                    val pack = PackRegistry[item.packId]
                    val hasDetail = pack?.draftExtra != null
                    val media = pack?.draftSummary?.invoke(item.packFields)
                    val hasFiles = item.files.size > 1
                    if (hasDetail || hasFiles || isCategoryEnabled) {
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (hasDetail) {
                                AssistChip(
                                    onClick = onOpenDetail,
                                    enabled = canInteract,
                                    modifier = Modifier.heightIn(min = 48.dp),
                                    label = { Text(media ?: stringResource(R.string.draft_media)) },
                                    leadingIcon = {
                                        Icon(painterResource(R.drawable.ic_settings), null,
                                            Modifier.size(18.dp))
                                    },
                                )
                            }
                            if (hasFiles) {
                                AssistChip(
                                    onClick = onOpenFiles,
                                    enabled = canInteract,
                                    modifier = Modifier.heightIn(min = 48.dp),
                                    label = {
                                        Text(stringResource(R.string.draft_files_selected,
                                            item.files.count { it.isSelected }, item.files.size))
                                    },
                                    leadingIcon = {
                                        Icon(painterResource(R.drawable.ic_file), null,
                                            Modifier.size(18.dp))
                                    },
                                )
                            }
                            if (isCategoryEnabled) {
                                val catName = category?.name ?: stringResource(R.string.task_uncategorized)
                                IconButton(onClick = onCategorize, enabled = isEnabled) {
                                    Icon(
                                        painterResource(
                                            category?.let { categoryIconRes(it.icon) }
                                                ?: if (item.categoryChoice == null) R.drawable.ic_refresh
                                                else R.drawable.ic_file
                                        ),
                                        stringResource(R.string.task_category_action, catName),
                                        Modifier.size(20.dp),
                                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
