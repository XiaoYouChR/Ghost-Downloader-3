package com.xychr.ghostdownloader.ui.components.draft

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.model.Category
import com.xychr.ghostdownloader.model.DraftItem
import com.xychr.ghostdownloader.packs.controlList
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes
import com.xychr.ghostdownloader.ui.util.fileTypeIconRes
import com.xychr.ghostdownloader.ui.util.formatSize

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun DraftCard(
    item: DraftItem,
    onRename: () -> Unit,
    onOpenOptions: () -> Unit,
    onCategorize: () -> Unit,
    onRefresh: () -> Unit,
    onSelectFiles: () -> Unit,
    onSelectControl: (id: String, value: String) -> Unit,
    modifier: Modifier = Modifier,
    category: Category? = null,
    isCategoryEnabled: Boolean = false,
    isEnabled: Boolean = true,
) {
    val canInteract = isEnabled && !item.isParsing && item.error == null
    val controls = item.packFields.controlList()

    Card(
        shape = MaterialTheme.shapes.largeIncreased,
        modifier = modifier.fillMaxWidth().animateContentSize(),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                val isFailed = item.error != null
                Icon(
                    painterResource(
                        if (isFailed) R.drawable.ic_info else fileTypeIconRes(item.name),
                    ), null,
                    Modifier.size(20.dp),
                    tint = if (isFailed) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    item.name.ifEmpty { item.url },
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                if (item.canEdit) {
                    IconButton(onClick = onRename, enabled = canInteract) {
                        Icon(painterResource(R.drawable.ic_edit), stringResource(R.string.task_detail_rename))
                    }
                    IconButton(onClick = onOpenOptions, enabled = canInteract) {
                        Icon(painterResource(R.drawable.ic_settings), stringResource(R.string.task_edit_options))
                    }
                }
                if (isCategoryEnabled) {
                    val catName = category?.name ?: stringResource(R.string.task_uncategorized)
                    IconButton(onClick = onCategorize, enabled = isEnabled) {
                        Icon(
                            painterResource(category?.let { categoryIconRes(it.icon) } ?: R.drawable.ic_file),
                            stringResource(R.string.task_category_action, catName),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }

            when {
                item.isParsing -> LinearProgressIndicator(Modifier.fillMaxWidth())
                item.error != null -> Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        engineText(item.error),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = onRefresh, enabled = isEnabled) {
                        Text(stringResource(R.string.draft_retry))
                    }
                }
                else -> Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    DraftControls(controls, isEnabled, onSelectControl, Modifier.weight(1f))
                    if (item.files.size > 1) {
                        AssistChip(onClick = onSelectFiles, enabled = isEnabled, label = {
                            Text(stringResource(R.string.draft_files_selected,
                                item.files.count { it.isSelected }, item.files.size))
                        })
                    }
                    if (item.fileSize > 0) Text(
                        formatSize(item.fileSize),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}
