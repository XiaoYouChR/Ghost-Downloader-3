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
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes
import com.xychr.ghostdownloader.ui.components.category.CategoryChoiceRow

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DraftCategoryField(categoryId: String?, categories: List<Category>, onSelect: (String?) -> Unit,
                       modifier: Modifier = Modifier, isEnabled: Boolean = true) {
    var isOpen by rememberSaveable { mutableStateOf(false) }
    val name = categories.firstOrNull { it.categoryId == categoryId }?.name
        ?: stringResource(if (categoryId == null) R.string.task_category_auto else R.string.task_uncategorized)
    OutlinedButton(onClick = { isOpen = true }, modifier = modifier, enabled = isEnabled) {
        Text(stringResource(R.string.task_category_value, name), Modifier.weight(1f, fill = false))
        Icon(painterResource(R.drawable.ic_chevron_right), null, Modifier.rotate(90f))
    }
    if (isOpen && isEnabled) ModalBottomSheet(onDismissRequest = { isOpen = false },
        sheetState = rememberBottomSheetState(initialValue = SheetValue.Hidden,
            enabledValues = setOf(SheetValue.Hidden, SheetValue.Expanded))) {
        Text(stringResource(R.string.task_change_category), Modifier.padding(horizontal = 24.dp, vertical = 12.dp),
            style = MaterialTheme.typography.titleLarge)
        LazyColumn(Modifier.selectableGroup()) {
            item { CategoryChoiceRow(stringResource(R.string.task_category_auto), categoryId == null,
                { onSelect(null); isOpen = false }, icon = R.drawable.ic_refresh) }
            item { CategoryChoiceRow(stringResource(R.string.task_uncategorized), categoryId == "",
                { onSelect(""); isOpen = false }) }
            items(categories, key = { it.categoryId }) { category ->
                CategoryChoiceRow(category.name, categoryId == category.categoryId,
                    { onSelect(category.categoryId); isOpen = false }, icon = categoryIconRes(category.icon))
            }
        }
    }
}
