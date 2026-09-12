package com.xychr.ghostdownloader.ui.pages.settings

import com.xychr.ghostdownloader.ui.navigation.*
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.Category
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.ConfirmDialog
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow

@Composable
fun CategoryPage(
    onNavigate: (Route) -> Unit,
    onBack: () -> Unit,
    viewModel: CategoryViewModel,
) {
    val categoryState by viewModel.state.collectAsStateWithLifecycle()
    val isSaving by viewModel.isSaving.collectAsStateWithLifecycle()
    val error by viewModel.error.collectAsStateWithLifecycle()
    val state = categoryState
    if (state == null) {
        SettingsPage(stringResource(R.string.category_manage), onBack) { LoadingRow() }
        return
    }
    var removing by remember { mutableStateOf<Category?>(null) }
    var isResetting by remember { mutableStateOf(false) }

    SettingsPage(stringResource(R.string.category_manage), onBack) {
        error?.let {
            Text(it)
        }
        Text(stringResource(R.string.task_category_rules_hint))
        SettingSection {
            SwitchSettingRow(
                title = stringResource(R.string.category_enabled),
                subtitle = stringResource(R.string.category_enabled_desc),
                checked = state.isEnabled,
                onCheckedChange = viewModel::setEnabled,
            )
        }

        SettingSection(title = stringResource(R.string.category_list)) {
            state.categories.forEachIndexed { index, category ->
                ActionSettingRow(
                    title = category.name,
                    subtitle = category.summary(),
                    onClick = { onNavigate(CategoryEditRoute(category.categoryId)) },
                    leading = {
                        Icon(
                            painter = painterResource(categoryIconRes(category.icon)),
                            contentDescription = null,
                        )
                    },
                    trailing = {
                        var isOpen by remember { mutableStateOf(false) }
                        Box {
                            IconButton(onClick = { isOpen = true }, enabled = !isSaving) {
                                Icon(painterResource(R.drawable.ic_more_vert), stringResource(R.string.action_more))
                            }
                            DropdownMenu(isOpen, onDismissRequest = { isOpen = false }) {
                                DropdownMenuItem(text = { Text(stringResource(R.string.task_category_up)) }, enabled = index > 0,
                                    onClick = { isOpen = false
                                        viewModel.setOrder(state.categories.map { it.categoryId }.toMutableList().apply {
                                            java.util.Collections.swap(this, index, index - 1)
                                        }) })
                                DropdownMenuItem(text = { Text(stringResource(R.string.task_category_down)) }, enabled = index < state.categories.lastIndex,
                                    onClick = { isOpen = false
                                        viewModel.setOrder(state.categories.map { it.categoryId }.toMutableList().apply {
                                            java.util.Collections.swap(this, index, index + 1)
                                        }) })
                                DropdownMenuItem(text = { Text(stringResource(R.string.action_delete)) }, onClick = {
                                    isOpen = false; removing = category
                                })
                            }
                        }
                    },
                )
            }

            ActionSettingRow(
                title = stringResource(R.string.category_add),
                onClick = { onNavigate(CategoryEditRoute()) },
            )
            ActionSettingRow(
                title = stringResource(R.string.category_reset),
                subtitle = stringResource(R.string.category_reset_desc),
                onClick = { isResetting = true },
            )
        }
    }

    removing?.let { category ->
        ConfirmDialog(
            title = stringResource(R.string.category_remove_title),
            message = stringResource(R.string.category_remove_message, category.name) + "\n" +
                stringResource(R.string.task_category_remove_hint),
            onDismiss = { removing = null },
            onConfirm = { viewModel.remove(category.categoryId) },
        )
    }

    if (isResetting) {
        ConfirmDialog(
            title = stringResource(R.string.category_reset),
            message = stringResource(R.string.category_reset_message) + "\n" +
                stringResource(R.string.task_category_remove_hint),
            onDismiss = { isResetting = false },
            onConfirm = viewModel::reset,
        )
    }
}

@Composable
private fun Category.summary(): String {
    val extensions = extensions.joinToString(", ").ifEmpty {
        stringResource(R.string.category_no_extension)
    }
    return "$extensions\n" + (folder ?: stringResource(R.string.category_default_folder))
}
