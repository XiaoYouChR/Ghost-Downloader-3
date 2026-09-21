package com.xychr.ghostdownloader.ui.platform

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext

class FolderPickerState(
    val launch: () -> Unit,
    val onPicked: (String) -> Unit,
    val isRejected: Boolean,
)

@Composable
fun rememberFolderPicker(onPicked: (String) -> Unit): FolderPickerState {
    val context = LocalContext.current
    var isRejected by remember { mutableStateOf(false) }
    val sink = rememberUpdatedState(onPicked)

    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree()
    ) { uri ->
        when {
            uri == null -> Unit
            uri.authority == EXTERNAL_STORAGE_AUTHORITY -> {
                isRejected = false
                val path = uri.toFolderPath()
                saveRecentFolder(context, path)
                sink.value(path)
            }

            else -> isRejected = true
        }
    }

    val launch = remember(launcher) { { launcher.launch(null) } }
    val deliver = remember { { path: String -> sink.value(path) } }
    return remember(launch, deliver, isRejected) { FolderPickerState(launch, deliver, isRejected) }
}
