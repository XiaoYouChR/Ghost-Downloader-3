package com.xychr.ghostdownloader.ui.pages.settings

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.model.Category
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.OptionsSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsEdit
import com.xychr.ghostdownloader.ui.components.settings.SettingsEditor
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage

// 键必须和引擎 category_service.py 的预设一致，桌面按这些值取 FluentIcon
private val ICON_KEYS = listOf(
    "VIDEO", "MUSIC", "PHOTO", "CHAT", "DOCUMENT", "ZIP_FOLDER", "APPLICATION", "HELP",
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
        SettingsPage(stringResource(R.string.category_edit), onBack) { LoadingRow() }
        return
    }
    val existing = state.categories.firstOrNull { it.categoryId == categoryId }
    val isCreating = categoryId.isEmpty()
    val defaultFolder = state.defaultFolder

    if (!isCreating && existing == null) {
        SettingsPage(stringResource(R.string.category_edit), onBack) {
            Text(stringResource(R.string.task_category_missing), Modifier.padding(16.dp))
        }
        return
    }

    // key 用 categoryId：数据到达时重新播种表单，之后用户的编辑不再被覆盖
    var name by rememberSaveable(categoryId) { mutableStateOf(existing?.name.orEmpty()) }
    var icon by rememberSaveable(categoryId) {
        mutableStateOf(existing?.icon ?: "DOCUMENT")
    }
    var extensions by rememberSaveable(categoryId) {
        mutableStateOf(existing?.extensions?.joinToString(", ").orEmpty())
    }
    var folder by rememberSaveable(categoryId) { mutableStateOf(existing?.folder.orEmpty()) }
    var folderError by rememberSaveable { mutableStateOf(false) }

    val folderPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree()
    ) { uri -> uri?.let {
        if (it.authority == "com.android.externalstorage.documents") {
            folder = it.toFolderPath()
            folderError = false
        } else folderError = true
    } }

    val category = Category(
        categoryId = categoryId, name = name.trim(), icon = icon,
        extensions = extensions.toExtensionList(), folder = folder.ifBlank { null },
    )
    SettingsEditor(
        title = stringResource(if (isCreating) R.string.category_add else R.string.category_edit),
        onBack = onBack,
        state = editState,
        isChanged = category != (existing ?: Category()),
        canSave = name.isNotBlank() && (folder.isBlank() || folder.startsWith("/") || folder.startsWith("{default}")),
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
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        )
        OutlinedTextField(folder, { folder = it }, enabled = !editState.isSaving,
            label = { Text(stringResource(R.string.category_folder)) },
            supportingText = { Text(stringResource(R.string.task_target_folder,
                folder.ifBlank { defaultFolder }.replace("{default}", defaultFolder))) },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp))
        Text(stringResource(R.string.task_category_rules_hint), Modifier.padding(horizontal = 16.dp))
        if (folderError) Text(stringResource(R.string.task_local_folder_only), Modifier.padding(horizontal = 16.dp))
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
            ActionSettingRow(
                title = stringResource(R.string.category_folder),
                subtitle = folder.ifEmpty { stringResource(R.string.category_default_folder) },
                onClick = { if (!editState.isSaving) folderPicker.launch(null) },
                trailing = {
                    IconButton(onClick = { folder = "" }, enabled = !editState.isSaving) {
                        Icon(
                            painter = painterResource(R.drawable.ic_restore),
                            contentDescription = stringResource(R.string.category_default_folder),
                        )
                    }
                },
            )
        }
    }
}

private fun String.toExtensionList(): List<String> =
    split(',', '，', ' ')
        .map { it.trim().removePrefix(".").lowercase() }
        .filter(String::isNotEmpty)
