package com.xychr.ghostdownloader.ui.components.settings

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.xychr.ghostdownloader.R
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class SettingsEditState(
    val isSaving: Boolean = false,
    val isSaved: Boolean = false,
    val hasError: Boolean = false,
)

// 保存跟随导航项而非 Composition，旋转屏幕不取消已经交给 Python 的写入。
class SettingsEdit : ViewModel() {
    private val editState = MutableStateFlow(SettingsEditState())
    val state = editState.asStateFlow()

    fun save(save: suspend () -> Unit) {
        if (editState.value.isSaving || editState.value.isSaved) return
        editState.value = SettingsEditState(isSaving = true)
        viewModelScope.launch {
            try {
                save()
                editState.value = SettingsEditState(isSaved = true)
            } catch (error: CancellationException) {
                editState.value = SettingsEditState()
                throw error
            } catch (_: Exception) {
                editState.value = SettingsEditState(hasError = true)
            }
        }
    }
}

@Composable
fun SettingsEditor(
    title: String,
    state: SettingsEditState,
    isChanged: Boolean,
    canSave: Boolean,
    onSave: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    saveLabel: String = stringResource(R.string.settings_action_save),
    canSubmitUnchanged: Boolean = false,
    onInvalid: () -> Unit = {},
    actions: @Composable RowScope.() -> Unit = {},
    snackbarHost: @Composable () -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    var shouldConfirmDiscard by rememberSaveable { mutableStateOf(false) }
    var shouldShowValidation by rememberSaveable { mutableStateOf(false) }
    val requestBack: () -> Unit = {
        if (!state.isSaving) {
            if (isChanged) shouldConfirmDiscard = true else onBack()
        }
    }
    val isKeyboardVisible = WindowInsets.ime.getBottom(LocalDensity.current) > 0
    BackHandler(enabled = !isKeyboardVisible) { requestBack() }
    LaunchedEffect(state.isSaved) { if (state.isSaved) onBack() }

    SettingsPage(
        title = title,
        onBack = requestBack,
        modifier = modifier,
        isEditing = true,
        isBusy = state.isSaving,
        snackbarHost = snackbarHost,
        actions = {
            actions()
            TextButton(
                onClick = {
                    shouldShowValidation = true
                    if (canSave) onSave() else onInvalid()
                },
                enabled = (isChanged || canSubmitUnchanged) && !state.isSaving && !state.isSaved,
            ) { Text(if (state.isSaving) stringResource(R.string.settings_edit_saving) else saveLabel) }
        },
    ) {
        if (state.isSaving) {
            LinearProgressIndicator(Modifier.fillMaxWidth())
            Text(stringResource(R.string.settings_edit_saving), Modifier.padding(horizontal = 16.dp))
        }
        if (state.hasError) {
            Text(
                stringResource(R.string.settings_edit_failed),
                modifier = Modifier.padding(horizontal = 16.dp),
                color = MaterialTheme.colorScheme.error,
            )
        }
        if (shouldShowValidation && !canSave) {
            Text(stringResource(R.string.settings_fix_fields), color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(horizontal = 16.dp))
        }
        content()
    }
    if (shouldConfirmDiscard) {
        AlertDialog(
            onDismissRequest = { shouldConfirmDiscard = false },
            title = { Text(stringResource(R.string.settings_edit_discard_title)) },
            text = { Text(stringResource(R.string.settings_edit_discard_message)) },
            confirmButton = {
                TextButton(onClick = onBack) { Text(stringResource(R.string.settings_edit_discard)) }
            },
            dismissButton = {
                TextButton(onClick = { shouldConfirmDiscard = false }) {
                    Text(stringResource(R.string.settings_edit_continue))
                }
            },
        )
    }
}
