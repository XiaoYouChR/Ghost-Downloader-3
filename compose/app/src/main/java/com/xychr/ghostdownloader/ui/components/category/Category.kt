package com.xychr.ghostdownloader.ui.components.category

import androidx.annotation.DrawableRes
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.Category

@Composable
fun CategoryChoiceRow(name: String, isSelected: Boolean, onSelect: () -> Unit,
                      modifier: Modifier = Modifier, @DrawableRes icon: Int = R.drawable.ic_file) {
    val background by animateColorAsState(if (isSelected) MaterialTheme.colorScheme.secondaryContainer
        else MaterialTheme.colorScheme.surfaceContainerLow, tween(150), label = "category-selection")
    Row(modifier.fillMaxWidth().heightIn(min = 56.dp)
        .background(background)
        .selectable(isSelected, role = Role.RadioButton, onClick = onSelect)
        .padding(horizontal = 24.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Icon(painterResource(icon), null, Modifier.size(24.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(name, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
        RadioButton(selected = isSelected, onClick = null)
    }
}

/** 选中的分类即筛选条件；再点一次取消选中就回到「全部」，所以没有「全部」这个 chip。 */
@Composable
fun CategoryFilterRow(categoryFilter: String?, categories: List<Category>, onSelect: (String?) -> Unit,
                      modifier: Modifier = Modifier) {
    LazyRow(modifier, horizontalArrangement = Arrangement.spacedBy(8.dp),
        contentPadding = PaddingValues(horizontal = 12.dp)) {
        item(key = "") {
            CategoryFilterChip(stringResource(R.string.task_uncategorized), categoryFilter == "",
                R.drawable.ic_file) { onSelect("".takeIf { categoryFilter != "" }) }
        }
        items(categories, key = { it.categoryId }) { category ->
            val isSelected = categoryFilter == category.categoryId
            CategoryFilterChip(category.name, isSelected, categoryIconRes(category.icon)) {
                onSelect(category.categoryId.takeIf { !isSelected })
            }
        }
    }
}

@Composable
private fun CategoryFilterChip(name: String, isSelected: Boolean, @DrawableRes icon: Int, onClick: () -> Unit) {
    FilterChip(selected = isSelected, onClick = onClick, label = { Text(name) },
        leadingIcon = {
            Icon(painterResource(if (isSelected) R.drawable.ic_check else icon), null,
                Modifier.size(FilterChipDefaults.IconSize))
        })
}

/**
 * 单选分类，选中即生效并关闭。保存失败由调用方用 snackbar 报告——
 * sheet 关掉之后就没地方显示错误了，错误处理留在页面这一层。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CategoryPicker(title: String, categories: List<Category>, selected: String?,
                   onSelect: (String?) -> Unit, onDismiss: () -> Unit,
                   modifier: Modifier = Modifier, hasAuto: Boolean = false, note: String? = null) {
    val choose: (String?) -> Unit = { onSelect(it); onDismiss() }
    ModalBottomSheet(onDismissRequest = onDismiss, modifier = modifier) {
        Text(title, Modifier.padding(horizontal = 24.dp, vertical = 12.dp),
            style = MaterialTheme.typography.titleLarge)
        note?.let {
            Text(it, Modifier.padding(horizontal = 24.dp).padding(bottom = 8.dp),
                style = MaterialTheme.typography.bodyMedium)
        }
        LazyColumn(Modifier.selectableGroup()) {
            if (hasAuto) item(key = "auto") {
                CategoryChoiceRow(stringResource(R.string.task_category_auto), selected == null,
                    { choose(null) }, icon = R.drawable.ic_refresh)
            }
            item(key = "") {
                CategoryChoiceRow(stringResource(R.string.task_uncategorized), selected == "", { choose("") })
            }
            items(categories, key = { it.categoryId }) { category ->
                CategoryChoiceRow(category.name, selected == category.categoryId,
                    { choose(category.categoryId) }, icon = categoryIconRes(category.icon))
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
