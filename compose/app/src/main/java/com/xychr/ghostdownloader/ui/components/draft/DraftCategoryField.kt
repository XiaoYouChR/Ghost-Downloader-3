package com.xychr.ghostdownloader.ui.components.draft
import com.xychr.ghostdownloader.model.*

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.category.CategoryPicker

@Composable
fun DraftCategoryField(categoryChoice: String?, categories: List<Category>, onSelect: (String?) -> Unit,
                       modifier: Modifier = Modifier, isEnabled: Boolean = true) {
    var isOpen by rememberSaveable { mutableStateOf(false) }
    val name = categories.firstOrNull { it.categoryId == categoryChoice }?.name
        ?: stringResource(if (categoryChoice == null) R.string.task_category_auto else R.string.task_uncategorized)
    OutlinedButton(onClick = { isOpen = true }, modifier = modifier, enabled = isEnabled) {
        Text(stringResource(R.string.task_category_value, name), Modifier.weight(1f, fill = false))
        Icon(painterResource(R.drawable.ic_chevron_right), null, Modifier.rotate(90f))
    }
    if (isOpen && isEnabled) CategoryPicker(
        title = stringResource(R.string.task_change_category),
        categories = categories,
        selected = categoryChoice,
        onSelect = onSelect,
        onDismiss = { isOpen = false },
        hasAuto = true,
    )
}
