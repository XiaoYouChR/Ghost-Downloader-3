package com.xychr.ghostdownloader.ui.components.draft
import com.xychr.ghostdownloader.model.*

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes
import com.xychr.ghostdownloader.ui.components.category.CategoryChoiceRow
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DraftCategorySheet(item: DraftItem, categories: List<Category>, error: String?,
                       onApply: suspend (String?) -> Boolean, onDismiss: () -> Unit,
                       modifier: Modifier = Modifier) {
    var selected by rememberSaveable { mutableStateOf(item.categoryChoice) }
    var isSaving by remember { mutableStateOf(false) }
    val saving by rememberUpdatedState(isSaving)
    val apply by rememberUpdatedState(onApply)
    val dismiss by rememberUpdatedState(onDismiss)
    val scope = rememberCoroutineScope()
    val isValid = selected.isNullOrEmpty() || categories.any { it.categoryId == selected }
    ModalBottomSheet(onDismissRequest = { if (!isSaving) onDismiss() }, modifier = modifier,
        sheetState = rememberBottomSheetState(initialValue = SheetValue.Hidden,
            enabledValues = setOf(SheetValue.Hidden, SheetValue.Expanded),
            confirmValueChange = { !saving })) {
        Column(Modifier.heightIn(max = 600.dp)) {
            Text(stringResource(R.string.task_change_category),
                Modifier.padding(horizontal = 24.dp, vertical = 12.dp), style = MaterialTheme.typography.titleLarge)
            Text(item.name, Modifier.padding(horizontal = 24.dp), style = MaterialTheme.typography.titleSmall)
            Text(stringResource(R.string.draft_category_apply_hint), Modifier.padding(horizontal = 24.dp, vertical = 8.dp),
                style = MaterialTheme.typography.bodyMedium)
            if (item.files.size > 1) Text(stringResource(R.string.draft_category_multiple),
                Modifier.padding(horizontal = 24.dp), style = MaterialTheme.typography.bodySmall)
            LazyColumn(Modifier.weight(1f, fill = false).selectableGroup()) {
                item { CategoryChoiceRow(stringResource(R.string.task_category_auto), selected == null,
                    { selected = null }, isEnabled = !isSaving, icon = R.drawable.ic_refresh) }
                item { CategoryChoiceRow(stringResource(R.string.task_uncategorized), selected == "",
                    { selected = "" }, isEnabled = !isSaving, icon = R.drawable.ic_file) }
                items(categories, key = { it.categoryId }) { category ->
                    CategoryChoiceRow(category.name, selected == category.categoryId,
                        { selected = category.categoryId }, isEnabled = !isSaving, icon = categoryIconRes(category.icon))
                }
            }
            if (!isValid) Text(stringResource(R.string.task_category_missing),
                Modifier.padding(horizontal = 24.dp), color = MaterialTheme.colorScheme.error)
            error?.let { Text(it, Modifier.padding(horizontal = 24.dp), color = MaterialTheme.colorScheme.error) }
            if (isSaving) LinearProgressIndicator(Modifier.fillMaxWidth())
            Row(Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.End) {
                TextButton(onClick = onDismiss, enabled = !isSaving) { Text(stringResource(R.string.action_cancel)) }
                Button(enabled = isValid && selected != item.categoryChoice && !isSaving, onClick = {
                    if (!isSaving) {
                        isSaving = true
                        val choice = selected
                        scope.launch {
                            try { if (apply(choice)) dismiss() }
                            finally { isSaving = false }
                        }
                    }
                }) { Text(stringResource(R.string.draft_apply)) }
            }
        }
    }
}
