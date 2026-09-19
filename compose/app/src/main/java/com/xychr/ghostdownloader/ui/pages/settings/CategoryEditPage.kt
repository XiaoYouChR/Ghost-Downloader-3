package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.Category
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.OptionsSettingRow
import com.xychr.ghostdownloader.ui.components.settings.PathSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsEdit
import com.xychr.ghostdownloader.ui.components.settings.SettingsEditor
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import com.xychr.ghostdownloader.ui.platform.rememberFolderPicker

private val ICON_KEYS = listOf(
    "VIDEO", "MUSIC", "PHOTO", "CHAT", "DOCUMENT", "ZIP_FOLDER", "APPLICATION",
    "BOOK", "CODE", "GAME", "LINK", "DATASET", "HELP",
)

@Composable
private fun iconOptions(): List<Pair<String, String>> = ICON_KEYS.zip(
    listOf(
        stringResource(R.string.category_icon_video),
        stringResource(R.string.category_icon_audio),
        stringResource(R.string.category_icon_image),
        stringResource(R.string.category_icon_subtitle),
        stringResource(R.string.category_icon_document),
        stringResource(R.string.category_icon_archive),
        stringResource(R.string.category_icon_program),
        stringResource(R.string.category_icon_book),
        stringResource(R.string.category_icon_code),
        stringResource(R.string.category_icon_game),
        stringResource(R.string.category_icon_link),
        stringResource(R.string.category_icon_dataset),
        stringResource(R.string.category_icon_other),
    )
)

@Composable
fun CategoryEditPage(
    categoryId: String,
    onBack: () -> Unit,
    viewModel: CategoryViewModel,
    edit: SettingsEdit = viewModel(),
) {
    val categoryState by viewModel.state.collectAsStateWithLifecycle()
    val editState by edit.state.collectAsStateWithLifecycle()
    val state = categoryState
    if (state == null) {
        SettingsScaffold(stringResource(R.string.category_edit), onBack) { LoadingRow() }
        return
    }
    val existing = state.categories.firstOrNull { it.categoryId == categoryId }
    val isCreating = categoryId.isEmpty()
    val defaultFolder = state.defaultFolder

    if (!isCreating && existing == null) {
        SettingsScaffold(stringResource(R.string.category_edit), onBack) {
            Text(stringResource(R.string.task_category_missing), Modifier.padding(16.dp))
        }
        return
    }

    var name by rememberSaveable(categoryId) { mutableStateOf(existing?.name.orEmpty()) }
    var icon by rememberSaveable(categoryId) {
        mutableStateOf(existing?.icon ?: "DOCUMENT")
    }
    var extensions by rememberSaveable(categoryId) {
        mutableStateOf(existing?.extensions?.joinToString(", ").orEmpty())
    }
    var folder by rememberSaveable(categoryId) { mutableStateOf(existing?.folder.orEmpty()) }
    val followsDefault = !folder.startsWith("/")
    val subfolder = if (followsDefault) folder.removePrefix("{default}").removePrefix("/") else ""

    val folderPicker = rememberFolderPicker { folder = it }

    val category = Category(
        categoryId = categoryId, name = name.trim(), icon = icon,
        extensions = extensions.toExtensionList(), folder = folder.ifBlank { null },
    )
    var shouldShowInvalid by rememberSaveable { mutableStateOf(false) }
    SettingsEditor(
        title = stringResource(if (isCreating) R.string.category_add else R.string.category_edit),
        onBack = onBack,
        state = editState,
        isChanged = category != (existing ?: Category()),
        canSave = name.isNotBlank(),
        saveLabel = stringResource(
            if (isCreating) R.string.settings_action_create else R.string.settings_action_save),
        onInvalid = { shouldShowInvalid = true },
        onSave = {
            edit.save {
                if (isCreating) viewModel.add(category) else viewModel.update(category)
            }
        },
    ) {
        OutlinedTextField(
            value = name,
            enabled = !editState.isSaving,
            onValueChange = { name = it },
            label = { Text(stringResource(R.string.category_name)) },
            isError = shouldShowInvalid && name.isBlank(),
            supportingText = if (shouldShowInvalid && name.isBlank()) {
                { Text(stringResource(R.string.category_name_required)) }
            } else null,
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        )
        Text(stringResource(R.string.task_category_rules_hint), Modifier.padding(horizontal = 16.dp))
        OutlinedTextField(
            value = extensions,
            enabled = !editState.isSaving,
            onValueChange = { extensions = it },
            label = { Text(stringResource(R.string.category_extensions)) },
            placeholder = { Text("mp4, mkv, avi") },
            supportingText = { Text(stringResource(R.string.category_extensions_desc)) },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        )
        SettingSection {
            OptionsSettingRow(
                title = stringResource(R.string.category_icon),
                value = icon,
                options = iconOptions(),
                onSelect = { icon = it },
                isEnabled = !editState.isSaving,
                leading = {
                    Icon(painterResource(categoryIconRes(icon)), contentDescription = null)
                },
            )
            SwitchSettingRow(
                title = stringResource(R.string.category_default_folder),
                subtitle = stringResource(R.string.category_follow_default_desc),
                checked = followsDefault,
                onCheckedChange = { follow -> folder = if (follow) "" else defaultFolder },
            )
            if (followsDefault) TextSettingRow(
                title = stringResource(R.string.category_subfolder),
                value = subfolder,
                onConfirm = { name ->
                    folder = name.trim().takeIf(String::isNotEmpty)?.let { "{default}/$it" }.orEmpty()
                },
                emptyHint = stringResource(R.string.category_subfolder_desc),
            ) else PathSettingRow(
                title = stringResource(R.string.category_folder),
                path = folder,
                picker = folderPicker,
            )
        }
        Text(
            stringResource(
                R.string.task_target_folder,
                folder.ifBlank { defaultFolder }.replace("{default}", defaultFolder),
            ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
    }
}

private fun String.toExtensionList(): List<String> =
    split(',', '，', ' ')
        .map { it.trim().removePrefix(".").lowercase() }
        .filter(String::isNotEmpty)
