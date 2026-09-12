package com.xychr.ghostdownloader.ui.pages

import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.navigation.*
import com.xychr.ghostdownloader.ui.components.*
import com.xychr.ghostdownloader.ui.components.task.*
import com.xychr.ghostdownloader.ui.util.*
import com.xychr.ghostdownloader.ui.components.category.CategorySheet
import com.xychr.ghostdownloader.ui.platform.openTaskFile
import com.xychr.ghostdownloader.ui.platform.openFolder

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.navigation.Route
import com.xychr.ghostdownloader.ui.navigation.TaskFilesRoute
import com.xychr.ghostdownloader.ui.navigation.TaskEditRoute
import com.xychr.ghostdownloader.ui.navigation.sharedContainer
import com.xychr.ghostdownloader.model.TaskError
import com.xychr.ghostdownloader.ui.util.formatSize
import com.xychr.ghostdownloader.ui.util.formatSizeProgress
import com.xychr.ghostdownloader.ui.util.formatSpeed
import com.xychr.ghostdownloader.i18n.engineText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import com.xychr.ghostdownloader.packs.PackRegistry
import kotlinx.serialization.json.JsonObject

class TaskDetailViewModel(private val taskId: String) : ViewModel() {

    private val _detail = MutableStateFlow(TaskDetail())
    val detail: StateFlow<TaskDetail> = _detail.asStateFlow()

    init {
        viewModelScope.launch { refresh() }
        viewModelScope.launch {
            EngineRepository.observe<List<TaskUiState>>("tasks").collect { tasks ->
                val task = tasks.find { it.id == taskId }
                if (task != null) {
                    _detail.value = _detail.value.copy(
                        status = task.status, canPause = task.canPause,
                        canStop = task.canStop, error = task.error,
                        hasOutputFile = task.hasOutputFile,
                    )
                }
            }
        }
        viewModelScope.launch {
            EngineRepository.observe<Map<String, TaskSnapshot>>("taskProgress").collect { progress ->
                progress[taskId]?.let { p ->
                    _detail.value = _detail.value.copy(
                        progress = p.progress, speed = p.speed, received = p.received,
                    )
                }
            }
        }
    }

    fun pause() = push("pause")
    fun stop() = push("stopTask")

    fun resume() {
        push("resume")
    }

    fun remove(shouldDeleteFiles: Boolean) {
        viewModelScope.launch { EngineRepository.invoke("remove", taskId, shouldDeleteFiles) }
    }

    suspend fun setName(name: String) {
        EngineRepository.invoke("setTaskName", taskId, name)
        refresh()
    }

    fun moveToFront() = push("moveToFront")

    fun redownload() {
        push("redownload")
    }

    suspend fun setCategory(categoryId: String) {
        EngineRepository.invoke("setTaskCategory", EngineRepository.encode(listOf(taskId)), categoryId)
        refresh()
    }

    private fun push(name: String, vararg args: Any?) {
        viewModelScope.launch {
            EngineRepository.invoke(name, taskId, *args)
            refresh()
        }
    }

    private suspend fun refresh() {
        runCatching { _detail.value = EngineRepository.query("taskDetail", taskId) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskDetailPage(
    taskId: String,
    onBack: () -> Unit,
    onNavigate: (Route) -> Unit,
    categories: CategoryState = CategoryState(),
    viewModel: TaskDetailViewModel = viewModel { TaskDetailViewModel(taskId) },
) {
    val detail by viewModel.detail.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }
    var isDeleting by remember { mutableStateOf(false) }
    var isRenaming by remember { mutableStateOf(false) }
    var shouldRedownload by remember { mutableStateOf(false) }
    var shouldCategorize by remember { mutableStateOf(false) }

    val copiedLabel = stringResource(R.string.task_detail_copied)
    fun copyUrl() {
        context.getSystemService(ClipboardManager::class.java)
            .setPrimaryClip(ClipData.newPlainText("url", detail.url))
        scope.launch { snackbarHostState.showSnackbar(copiedLabel) }
    }

    Scaffold(
        modifier = Modifier.sharedContainer("task-$taskId"),
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = detail.name.ifEmpty { detail.id },
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            painter = painterResource(R.drawable.ic_arrow_back),
                            contentDescription = stringResource(R.string.action_back),
                        )
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
        ) {
            ProgressSection(detail)

            Spacer(Modifier.height(16.dp))
            ActionRow(
                detail = detail,
                onPause = { if (detail.canStop) viewModel.stop() else viewModel.pause() },
                onResume = { viewModel.resume() },
                onDelete = { isDeleting = true },
                onCopyUrl = ::copyUrl,
                onMoveToFront = viewModel::moveToFront,
                onRedownload = { shouldRedownload = true },
                onOpenFile = {
                    if (detail.hasOutputFile) context.openTaskFile(detail.outputPath)
                    else context.openFolder(detail.outputFolder)
                },
                onOpenFolder = { context.openFolder(detail.outputFolder) },
            )

            Spacer(Modifier.height(16.dp))
            InfoSection(detail, onRename = { isRenaming = true }, onCopyUrl = ::copyUrl)
            if (categories.isEnabled) TextButton(onClick = { shouldCategorize = true }) {
                Text(stringResource(R.string.task_category_value, categories.categories.firstOrNull {
                    it.categoryId == detail.categoryId
                }?.name ?: stringResource(R.string.task_uncategorized)))
            }
            if (detail.canEdit && detail.status != TaskStatus.COMPLETED) TextButton(onClick = {
                onNavigate(TaskEditRoute(taskId))
            }) { Text(stringResource(R.string.task_edit_options)) }

            if (detail.files.isNotEmpty()) {
                Spacer(Modifier.height(16.dp))
                TextButton(onClick = { onNavigate(TaskFilesRoute(taskId)) }) {
                    Text(stringResource(R.string.task_choose_files))
                }
                FilesSection(detail)
            }
            if (detail.packFields.isNotEmpty()) {
                Spacer(Modifier.height(16.dp))
                PackRegistry[detail.packId]?.detailExtra?.invoke(detail.packFields)
            }
            detail.error?.let {
                Spacer(Modifier.height(16.dp))
                ErrorSection(it)
            }

            Spacer(Modifier.height(24.dp))
        }
    }

    if (isDeleting) {
        DeleteTaskDialog(
            onDismiss = { isDeleting = false },
            onConfirm = { shouldDeleteFiles ->
                viewModel.remove(shouldDeleteFiles)
                isDeleting = false
                onBack()
            },
        )
    }
    if (shouldCategorize) CategorySheet(categories.categories,
        initialCategoryId = toCategoryId(detail.categoryId, categories.categories), taskCount = 1,
        onApply = { categoryId ->
            viewModel.setCategory(categoryId)
        }, onDismiss = { shouldCategorize = false })

    if (isRenaming) {
        RenameDialog(
            current = detail.name,
            onDismiss = { isRenaming = false },
            onConfirm = {
                viewModel.setName(it)
            },
        )
    }
    if (shouldRedownload) AlertDialog(
        onDismissRequest = { shouldRedownload = false },
        title = { Text(stringResource(R.string.task_detail_redownload)) },
        text = { Text(stringResource(R.string.task_redownload_warning)) },
        confirmButton = { TextButton(onClick = {
            shouldRedownload = false
            viewModel.redownload()
        }) { Text(stringResource(R.string.task_detail_redownload)) } },
        dismissButton = { TextButton(onClick = { shouldRedownload = false }) {
            Text(stringResource(R.string.action_cancel))
        } },
    )
}

@Composable
private fun ProgressSection(detail: TaskDetail) {
    val text = when {
        detail.status == TaskStatus.FAILED -> stringResource(R.string.task_status_failed)
        detail.status == TaskStatus.COMPLETED -> stringResource(R.string.task_status_completed) +
            formatTimestamp(detail.completedAt).takeIf { it.isNotEmpty() }?.let { " · $it" }.orEmpty()
        detail.status == TaskStatus.WAITING -> stringResource(R.string.task_status_waiting)
        detail.statusText.isNotEmpty() -> engineText(detail.statusText, emptyMap())
        detail.status == TaskStatus.PAUSED -> stringResource(R.string.task_status_paused)
        detail.status == TaskStatus.RUNNING ->
            "${formatSpeed(detail.speed)} · ${detail.progress.toInt()}%"
        else -> ""
    }
    Text(
        text = text,
        style = MaterialTheme.typography.bodyLarge,
        color = if (detail.status == TaskStatus.FAILED) MaterialTheme.colorScheme.error
        else MaterialTheme.colorScheme.onSurfaceVariant,
    )

    Spacer(Modifier.height(8.dp))

    if (detail.progressMode != "hidden" && detail.status != TaskStatus.COMPLETED && detail.status != TaskStatus.FAILED) {
        TaskProgress(detail.status, detail.progress,
            detail.progressMode == "indeterminate" || detail.fileSize <= 0 && detail.progress <= 0)
    }

    Spacer(Modifier.height(4.dp))
    Row {
        Text(
            text = formatSizeProgress(detail.received, detail.fileSize),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (detail.secondarySpeed > 0) Text(
            text = " · ↑ ${formatSpeed(detail.secondarySpeed)}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ActionRow(
    detail: TaskDetail,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onDelete: () -> Unit,
    onCopyUrl: () -> Unit,
    onMoveToFront: () -> Unit,
    onRedownload: () -> Unit,
    onOpenFile: () -> Unit,
    onOpenFolder: () -> Unit,
) {
    var isMenuOpen by remember { mutableStateOf(false) }

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        when (detail.status) {
            TaskStatus.RUNNING -> Button(onClick = onPause, enabled = detail.canStop || detail.canPause) {
                Icon(painterResource(if (detail.canStop) R.drawable.ic_check else R.drawable.ic_pause), null)
                Text(stringResource(if (detail.canStop) R.string.task_stop_save else R.string.action_pause), Modifier.padding(start = 4.dp))
            }

            TaskStatus.PAUSED, TaskStatus.WAITING, TaskStatus.FAILED -> Button(onClick = onResume) {
                Icon(painterResource(R.drawable.ic_play), null)
                Text(stringResource(R.string.action_resume), Modifier.padding(start = 4.dp))
            }

            TaskStatus.COMPLETED -> Button(onClick = onOpenFile) {
                Icon(painterResource(R.drawable.ic_open_in_new), null)
                Text(stringResource(R.string.task_detail_open_file), Modifier.padding(start = 4.dp))
            }
        }

        if (detail.status == TaskStatus.COMPLETED) {
            OutlinedButton(onClick = onOpenFolder) {
                Icon(painterResource(R.drawable.ic_folder), null)
                Text(
                    text = stringResource(R.string.task_detail_open_folder),
                    modifier = Modifier.padding(start = 4.dp),
                )
            }
        }

        OutlinedButton(
            onClick = onDelete,
            colors = ButtonDefaults.outlinedButtonColors(
                contentColor = MaterialTheme.colorScheme.error,
            ),
        ) {
            Icon(painterResource(R.drawable.ic_delete), null)
            Text(stringResource(R.string.action_delete), Modifier.padding(start = 4.dp))
        }

        Spacer(Modifier.weight(1f))

        IconButton(onClick = { isMenuOpen = true }) {
            Icon(
                painter = painterResource(R.drawable.ic_more_vert),
                contentDescription = stringResource(R.string.action_more),
            )
        }
        DropdownMenu(expanded = isMenuOpen, onDismissRequest = { isMenuOpen = false }) {
            DropdownMenuItem(
                text = { Text(stringResource(R.string.task_detail_copy_url)) },
                onClick = {
                    onCopyUrl()
                    isMenuOpen = false
                },
            )
            if (detail.status == TaskStatus.WAITING || detail.status == TaskStatus.PAUSED) {
                DropdownMenuItem(
                    text = { Text(stringResource(R.string.task_detail_move_to_front)) },
                    onClick = {
                        onMoveToFront()
                        isMenuOpen = false
                    },
                )
            }
            DropdownMenuItem(
                text = { Text(stringResource(R.string.task_detail_redownload)) },
                onClick = {
                    onRedownload()
                    isMenuOpen = false
                },
            )
        }
    }
}

@Composable
private fun InfoSection(detail: TaskDetail, onRename: () -> Unit, onCopyUrl: () -> Unit) {
    SectionTitle(stringResource(R.string.task_detail_info))

    ListItem(
        supportingContent = { Text(detail.name, maxLines = 2, overflow = TextOverflow.Ellipsis) },
        trailingContent = if (detail.canRename) {
            {
                IconButton(onClick = onRename) {
                    Icon(
                        painter = painterResource(R.drawable.ic_edit),
                        contentDescription = stringResource(R.string.task_detail_rename),
                    )
                }
            }
        } else {
            null
        },
    ) { Text(stringResource(R.string.task_detail_name)) }
    ListItem(
        supportingContent = { Text(detail.url, maxLines = 2, overflow = TextOverflow.Ellipsis) },
        trailingContent = {
            IconButton(onClick = onCopyUrl) {
                Icon(
                    painter = painterResource(R.drawable.ic_copy),
                    contentDescription = stringResource(R.string.task_detail_copy_url),
                )
            }
        },
    ) { Text(stringResource(R.string.task_detail_url)) }
    if (detail.createdAt > 0) {
        ListItem(
            supportingContent = { Text(formatTimestamp(detail.createdAt)) },
        ) { Text(stringResource(R.string.task_detail_created)) }
    }
}

@Composable
private fun FilesSection(detail: TaskDetail) {
    SectionTitle(stringResource(R.string.task_detail_files))

    detail.files.forEach { file ->
        ListItem(
            supportingContent = { Text(fileStatusText(file) + " · " + formatSize(file.size)) },
        ) { Text(file.path, style = MaterialTheme.typography.bodyMedium, maxLines = 2) }
    }
}

@Composable
private fun fileStatusText(file: TaskFile): String = when {
    !file.isSelected -> stringResource(R.string.task_file_unselected)
    file.isCompleted -> stringResource(R.string.task_status_completed)
    file.progress > 0.0 -> "${file.progress.toInt()}%"
    else -> stringResource(R.string.task_status_waiting)
}

@Composable
private fun ErrorSection(error: TaskError) {
    SectionTitle(stringResource(R.string.task_detail_error))
    Text(
        text = engineText(error.message, error.params),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.error,
    )
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(bottom = 4.dp),
    )
}

@Composable
private fun DeleteTaskDialog(onDismiss: () -> Unit, onConfirm: (Boolean) -> Unit) {
    var shouldDeleteFiles by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.task_detail_delete_confirm)) },
        text = {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .toggleable(
                        value = shouldDeleteFiles,
                        role = Role.Checkbox,
                        onValueChange = { shouldDeleteFiles = it },
                    ),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Checkbox(checked = shouldDeleteFiles, onCheckedChange = null)
                Text(
                    text = stringResource(R.string.task_detail_delete_files),
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(shouldDeleteFiles) }) {
                Text(
                    text = stringResource(R.string.action_delete),
                    color = MaterialTheme.colorScheme.error,
                )
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) }
        },
    )
}

@Composable
private fun RenameDialog(current: String, onDismiss: () -> Unit, onConfirm: suspend (String) -> Unit) {
    var text by remember { mutableStateOf(current) }
    var isSaving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
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
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    isSaving = true
                    scope.launch {
                        try { onConfirm(text.trim()); onDismiss() }
                        catch (failure: Exception) { error = failure.message }
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
