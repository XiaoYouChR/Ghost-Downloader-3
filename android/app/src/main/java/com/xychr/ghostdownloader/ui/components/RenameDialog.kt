package com.xychr.ghostdownloader.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.i18n.toTaskError
import com.xychr.ghostdownloader.model.TaskError
import kotlinx.coroutines.launch

@Composable
fun RenameDialog(current: String, onDismiss: () -> Unit, onConfirm: suspend (String) -> Unit) {
    var text by remember { mutableStateOf(current) }
    var isSaving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<TaskError?>(null) }
    val scope = rememberCoroutineScope()

    AlertDialog(
        onDismissRequest = { if (!isSaving) onDismiss() },
        title = { Text(stringResource(R.string.task_detail_rename)) },
        text = {
            Column {
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    enabled = !isSaving,
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                ErrorText(error)
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    isSaving = true
                    scope.launch {
                        try { onConfirm(text.trim()); onDismiss() }
                        catch (failure: Exception) { error = failure.toTaskError() }
                        finally { isSaving = false }
                    }
                },
                enabled = !isSaving && text.isNotBlank() && text.trim() != current,
            ) { Text(stringResource(R.string.action_ok)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !isSaving) { Text(stringResource(R.string.action_cancel)) }
        },
    )
}
