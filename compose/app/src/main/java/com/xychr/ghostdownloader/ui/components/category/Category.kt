package com.xychr.ghostdownloader.ui.components.category

import androidx.annotation.DrawableRes
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.Category
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable
fun CategoryChoiceRow(name: String, isSelected: Boolean, onSelect: () -> Unit,
                      modifier: Modifier = Modifier, isEnabled: Boolean = true,
                      @DrawableRes icon: Int = R.drawable.ic_file) {
    val background by animateColorAsState(if (isSelected) MaterialTheme.colorScheme.secondaryContainer
        else MaterialTheme.colorScheme.surfaceContainerLow, tween(150), label = "category-selection")
    Row(modifier.fillMaxWidth().heightIn(min = 56.dp)
        .background(background)
        .selectable(isSelected, enabled = isEnabled, role = Role.RadioButton, onClick = onSelect)
        .padding(horizontal = 24.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Icon(painterResource(icon), null, Modifier.size(24.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(name, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
        RadioButton(selected = isSelected, onClick = null, enabled = isEnabled)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CategoryFilter(categoryId: String?, categories: List<Category>, onSelect: (String?) -> Unit,
                   modifier: Modifier = Modifier) {
    var isOpen by rememberSaveable { mutableStateOf(false) }
    val name = categories.firstOrNull { it.categoryId == categoryId }?.name
        ?: stringResource(if (categoryId == null) R.string.task_filter_all else R.string.task_uncategorized)
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        FilterChip(selected = categoryId != null, onClick = { isOpen = true },
            modifier = Modifier.weight(1f, fill = false),
            label = { Text(stringResource(R.string.task_category_value, name)) },
            trailingIcon = { Icon(painterResource(R.drawable.ic_chevron_right), null, Modifier.rotate(90f)) })
        if (categoryId != null) IconButton(onClick = { onSelect(null) }) {
            Icon(painterResource(R.drawable.ic_close), stringResource(R.string.task_clear_category_filter))
        }
    }
    if (isOpen) ModalBottomSheet(onDismissRequest = { isOpen = false },
        sheetState = rememberBottomSheetState(initialValue = SheetValue.Hidden,
            enabledValues = setOf(SheetValue.Hidden, SheetValue.Expanded))) {
        Text(stringResource(R.string.task_filter_category), Modifier.padding(horizontal = 24.dp, vertical = 12.dp),
            style = MaterialTheme.typography.titleLarge)
        LazyColumn(Modifier.selectableGroup()) {
            item { CategoryChoiceRow(stringResource(R.string.task_filter_all), categoryId == null,
                { onSelect(null); isOpen = false }) }
            item { CategoryChoiceRow(stringResource(R.string.task_uncategorized), categoryId == "",
                { onSelect(""); isOpen = false }) }
            items(categories, key = { it.categoryId }) { category ->
                CategoryChoiceRow(category.name, categoryId == category.categoryId,
                    { onSelect(category.categoryId); isOpen = false }, icon = categoryIconRes(category.icon))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CategorySheet(categories: List<Category>, initialCategoryId: String?, taskCount: Int,
                  onApply: suspend (String) -> Unit, onDismiss: () -> Unit, modifier: Modifier = Modifier) {
    var selected by rememberSaveable { mutableStateOf(initialCategoryId) }
    var isSaving by remember { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val saving by rememberUpdatedState(isSaving)
    val apply by rememberUpdatedState(onApply)
    val dismiss by rememberUpdatedState(onDismiss)
    val failureText = stringResource(R.string.task_category_save_failed)
    val isValid = selected == "" || categories.any { it.categoryId == selected }
    ModalBottomSheet(onDismissRequest = { if (!isSaving) onDismiss() }, modifier = modifier,
        sheetState = rememberBottomSheetState(initialValue = SheetValue.Hidden,
            enabledValues = setOf(SheetValue.Hidden, SheetValue.Expanded),
            confirmValueChange = { !saving })) {
        Column(Modifier.heightIn(max = 600.dp)) {
            Text(stringResource(if (taskCount == 1) R.string.task_change_category else R.string.task_change_categories,
                taskCount), Modifier.padding(horizontal = 24.dp, vertical = 12.dp),
                style = MaterialTheme.typography.titleLarge)
            Text(stringResource(R.string.task_category_label_only), Modifier.padding(horizontal = 24.dp),
                style = MaterialTheme.typography.bodyMedium)
            if (initialCategoryId == null) Text(stringResource(R.string.task_categories_mixed),
                Modifier.padding(horizontal = 24.dp, vertical = 8.dp), style = MaterialTheme.typography.bodyMedium)
            LazyColumn(Modifier.weight(1f, fill = false).selectableGroup()) {
                item { CategoryChoiceRow(stringResource(R.string.task_uncategorized), selected == "",
                    { selected = ""; error = null }, isEnabled = !isSaving) }
                items(categories, key = { it.categoryId }) { category ->
                    CategoryChoiceRow(category.name, selected == category.categoryId,
                        { selected = category.categoryId; error = null }, isEnabled = !isSaving,
                        icon = categoryIconRes(category.icon))
                }
            }
            if (!isValid && selected != null) Text(stringResource(R.string.task_category_missing),
                Modifier.padding(horizontal = 24.dp), color = MaterialTheme.colorScheme.error)
            error?.let { Text(it, Modifier.padding(horizontal = 24.dp), color = MaterialTheme.colorScheme.error) }
            if (isSaving) LinearProgressIndicator(Modifier.fillMaxWidth())
            Row(Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.End) {
                TextButton(onClick = onDismiss, enabled = !isSaving) { Text(stringResource(R.string.action_cancel)) }
                Button(enabled = isValid && selected != initialCategoryId && !isSaving, onClick = {
                    if (!isSaving) {
                        isSaving = true
                        error = null
                        val categoryId = requireNotNull(selected)
                        scope.launch {
                            try {
                                apply(categoryId)
                                dismiss()
                            } catch (failure: CancellationException) { throw failure }
                            catch (failure: Exception) { error = failure.message ?: failureText }
                            finally { isSaving = false }
                        }
                    }
                }) { Text(stringResource(R.string.task_apply)) }
            }
        }
    }
}

fun categoryIconRes(icon: String): Int = when (icon) {
    "VIDEO" -> R.drawable.ic_cat_video
    "MUSIC" -> R.drawable.ic_cat_music
    "PHOTO" -> R.drawable.ic_cat_photo
    "CHAT" -> R.drawable.ic_cat_chat
    "ZIP_FOLDER" -> R.drawable.ic_cat_archive
    "APPLICATION" -> R.drawable.ic_cat_application
    "HELP" -> R.drawable.ic_cat_other
    else -> R.drawable.ic_cat_document
}
