package com.xychr.ghostdownloader.ui.components.draft
import com.xychr.ghostdownloader.model.*

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.animation.animateContentSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.util.formatSize
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes
import com.xychr.ghostdownloader.ui.components.category.CategoryAction

@Composable
fun DraftCard(
    item: DraftItem,
    isProbing: Boolean,
    probeError: String?,
    onOpen: () -> Unit,
    onRetry: () -> Unit,
    onCategorize: () -> Unit,
    modifier: Modifier = Modifier,
    category: Category? = null,
    isCategoryEnabled: Boolean = false,
    isCategoryOpen: Boolean = false,
    isEnabled: Boolean = true,
) {
    Card(onClick = onOpen, enabled = isEnabled && !item.isParsing && item.error == null,
        modifier = modifier.fillMaxWidth().animateContentSize()) {
        Column(Modifier.padding(16.dp)) {
            Text(item.name.ifEmpty { item.url }, style = MaterialTheme.typography.titleMedium,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (item.name.isNotEmpty()) Text(item.url, maxLines = 1, overflow = TextOverflow.Ellipsis,
                style = MaterialTheme.typography.bodySmall)
            when {
                item.isParsing -> {
                    Text(stringResource(R.string.draft_parsing))
                    LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 8.dp))
                }
                item.error != null -> Text(engineText(item.error.message, item.error.params),
                    color = MaterialTheme.colorScheme.error)
                else -> {
                    Text(if (item.fileSize < 0) "—" else formatSize(item.fileSize), style = MaterialTheme.typography.bodySmall)
                    if (isCategoryEnabled) {
                        val name = category?.name ?: stringResource(R.string.task_uncategorized)
                        CategoryAction(if (item.categoryChoice == null)
                            stringResource(R.string.draft_category_auto_result, name) else name,
                            category?.let { categoryIconRes(it.icon) }
                                ?: if (item.categoryChoice == null) R.drawable.ic_refresh else R.drawable.ic_file,
                            onCategorize, isEnabled = isEnabled, isOpen = isCategoryOpen)
                    }
                    if (item.targetFolder.isNotEmpty()) Row(verticalAlignment = Alignment.Top,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(painterResource(R.drawable.ic_folder), null, Modifier.size(18.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(stringResource(R.string.task_target_folder, item.targetFolder),
                            style = MaterialTheme.typography.bodySmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                    if (item.files.size > 1) Text(stringResource(R.string.draft_files_selected,
                        item.files.count { it.isSelected }, item.files.size))
                    if (isProbing) {
                        Text(stringResource(R.string.draft_media_loading))
                        LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 8.dp))
                    }
                    if (probeError != null) {
                        Text(probeError, color = MaterialTheme.colorScheme.error)
                        TextButton(onClick = onRetry) { Text(stringResource(R.string.draft_retry)) }
                    }
                }
            }
        }
    }
}
