package com.xychr.ghostdownloader.ui.pages

import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.navigation.*
import com.xychr.ghostdownloader.ui.components.*
import com.xychr.ghostdownloader.ui.components.task.*
import com.xychr.ghostdownloader.ui.util.*
import com.xychr.ghostdownloader.ui.components.category.CategoryPicker
import com.xychr.ghostdownloader.ui.platform.openTaskFile
import com.xychr.ghostdownloader.ui.platform.openFolder
import com.xychr.ghostdownloader.ui.platform.shareTaskFile
import com.xychr.ghostdownloader.ui.platform.shareText

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
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
import com.xychr.ghostdownloader.ui.components.notice.LocalSnackbar
import com.xychr.ghostdownloader.ui.navigation.Route
import com.xychr.ghostdownloader.ui.navigation.TaskFilesRoute
import com.xychr.ghostdownloader.ui.navigation.TaskEditRoute
import com.xychr.ghostdownloader.ui.navigation.sharedContainer
import com.xychr.ghostdownloader.model.TaskError
import com.xychr.ghostdownloader.ui.util.formatSize
import com.xychr.ghostdownloader.ui.util.formatSizeProgress
import com.xychr.ghostdownloader.ui.util.formatSpeed
import com.xychr.ghostdownloader.i18n.engineText
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
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
            val tasks = engineRepository.observe<List<TaskUiState>>("tasks")
            val activeTasks = engineRepository.observe<Map<String, TaskUiState>>("taskProgress")
            tasks.combine(activeTasks) { list, active ->
                list.find { it.id == taskId }?.update(active)
            }.collect { task ->
                if (task != null) _detail.value = _detail.value.copy(
                    status = task.status, canPause = task.canPause,
                    canStop = task.canStop, error = task.error,
                    hasOutputFile = task.hasOutputFile,
                    isOutputFolder = task.isOutputFolder,
                    isFileMissing = task.isFileMissing,
                    progress = task.progress, speed = task.speed, received = task.received,
                )
            }
        }
    }

    fun pause() = push("pause")
    fun stop() = push("stopTask")

    fun resume() {
        push("resume")
    }

    fun remove(shouldDeleteFiles: Boolean) {
        viewModelScope.launch { engineRepository.invoke("remove", taskId, shouldDeleteFiles) }
    }

    suspend fun setName(name: String) {
        engineRepository.invoke("setTaskName", taskId, name)
        refresh()
    }

    fun moveToFront() {
        viewModelScope.launch {
            engineRepository.invoke("moveToFront", engineRepository.encode(listOf(taskId)))
            refresh()
        }
    }

    fun redownload() {
        push("redownload")
    }

    suspend fun setCategory(categoryId: String) {
        engineRepository.invoke("setTaskCategory", engineRepository.encode(listOf(taskId)), categoryId)
        refresh()
    }

    private fun push(name: String, vararg args: Any?) {
        viewModelScope.launch {
            engineRepository.invoke(name, taskId, *args)
            refresh()
        }
    }

    private suspend fun refresh() {
        runCatching { _detail.value = engineRepository.query("taskDetail", taskId) }
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
    val snackbarHostState = LocalSnackbar.current
    var isDeleting by remember { mutableStateOf(false) }
    var isRenaming by remember { mutableStateOf(false) }
    var shouldRedownload by remember { mutableStateOf(false) }
    var shouldCategorize by remember { mutableStateOf(false) }
    var isHashing by remember { mutableStateOf(false) }

    val copiedLabel = stringResource(R.string.task_detail_copied)
    val categorySaveFailed = stringResource(R.string.task_category_save_failed)
    fun copyUrl() {
        context.getSystemService(ClipboardManager::class.java)
            .setPrimaryClip(ClipData.newPlainText("url", detail.url))
        scope.launch { snackbarHostState.showSnackbar(copiedLabel) }
    }
    fun copyPath() {
        context.getSystemService(ClipboardManager::class.java)
            .setPrimaryClip(ClipData.newPlainText("path", detail.outputFolder))
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
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 0.dp),
        ) {
            item { ProgressSection(detail) }

            item {
                Spacer(Modifier.height(16.dp))
                ActionRow(detail) { action ->
                    when (action) {
                        TaskAction.STOP -> viewModel.stop()
                        TaskAction.PAUSE -> viewModel.pause()
                        TaskAction.RESUME -> viewModel.resume()
                        TaskAction.OPEN_FILE -> context.openTaskFile(detail.outputPath)
                        TaskAction.OPEN_FOLDER -> context.openFolder(detail.outputFolder)
                        TaskAction.SHARE_FILE -> if (!context.shareTaskFile(detail.outputPath)) {
                            scope.launch {
                                snackbarHostState.showSnackbar(context.getString(R.string.task_share_unavailable))
                            }
                        }
                        TaskAction.COPY_URL -> copyUrl()
                        TaskAction.COPY_PATH -> copyPath()
                        TaskAction.SHARE_URL -> context.shareText(detail.url)
                        TaskAction.MOVE_TO_FRONT -> viewModel.moveToFront()
                        TaskAction.REDOWNLOAD -> shouldRedownload = true
                        TaskAction.VERIFY_HASH -> isHashing = true
                        TaskAction.DELETE -> isDeleting = true
                        TaskAction.FILES, TaskAction.EDIT, TaskAction.CATEGORY -> Unit
                    }
                }
            }

            item {
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
            }

            if (detail.files.isNotEmpty()) {
                item {
                    Spacer(Modifier.height(16.dp))
                    SectionTitle(stringResource(R.string.task_detail_files))
                    TextButton(onClick = { onNavigate(TaskFilesRoute(taskId)) }) {
                        Text(stringResource(toFileSelectLabel(detail.fileSelectKind)))
                    }
                }
                items(detail.files, key = { it.index }) { file -> TaskFileRow(file) }
            }
            if (detail.packFields.isNotEmpty()) {
                item {
                    Spacer(Modifier.height(16.dp))
                    PackRegistry[detail.packId]?.detailExtra?.invoke(detail.packFields)
                }
            }
            detail.error?.let {
                item {
                    Spacer(Modifier.height(16.dp))
                    ErrorSection(it)
                }
            }

            item { Spacer(Modifier.height(24.dp)) }
        }
    }

    if (isHashing) HashSheet(
        taskId = detail.id,
        name = detail.name,
        onDismiss = { isHashing = false },
    )
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
    if (shouldCategorize) CategoryPicker(
        title = stringResource(R.string.task_change_category),
        categories = categories.categories,
        selected = detail.categoryId,
        onSelect = { choice ->
            scope.launch {
                try {
                    viewModel.setCategory(choice.orEmpty())
                } catch (failure: CancellationException) {
                    throw failure
                } catch (failure: Exception) {
                    snackbarHostState.showSnackbar(context.engineText(failure))
                }
            }
        },
        onDismiss = { shouldCategorize = false },
        note = stringResource(R.string.task_category_label_only),
    )

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
    TaskStatusLine(
        status = detail.status,
        error = detail.error,
        statusText = detail.statusText,
        completedAt = detail.completedAt,
        speed = detail.speed,
        progress = detail.progress,
        isFileMissing = detail.isFileMissing,
        style = MaterialTheme.typography.bodyLarge,
        maxLines = Int.MAX_VALUE,
    )

    Spacer(Modifier.height(8.dp))

    if (detail.progressMode != "hidden" && detail.status != TaskStatus.COMPLETED && detail.status != TaskStatus.FAILED) {
        TaskProgress(detail.status, detail.progress,
            detail.progressMode == "indeterminate" || detail.fileSize <= 0 && detail.progress <= 0)
    }

    Spacer(Modifier.height(4.dp))
    Row(
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = formatSizeProgress(detail.received, detail.fileSize),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (detail.secondarySpeed > 0) Text(
            text = "↑ ${formatSpeed(detail.secondarySpeed)}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ActionRow(detail: TaskDetail, onAction: (TaskAction) -> Unit) {
    val main = buildTaskMainAction(detail)
    val menu = buildList {
        buildVerifyHashAction(detail)?.let { add(it) }
        add(copyUrlSpec)
        add(shareUrlSpec)
        if (detail.status == TaskStatus.WAITING || detail.status == TaskStatus.PAUSED) add(moveToFrontSpec)
        if (main.action != TaskAction.REDOWNLOAD) add(redownloadSpec)
        add(deleteSpec)
    }

    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(
            modifier = Modifier.weight(1f).horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Button(onClick = { onAction(main.action) }, enabled = main.isEnabled) {
                Icon(painterResource(main.icon), null)
                Text(stringResource(main.label), Modifier.padding(start = 4.dp))
            }
            if (main.action == TaskAction.OPEN_FILE) {
                OutlinedButton(onClick = { onAction(TaskAction.SHARE_FILE) }) {
                    Icon(painterResource(shareFileSpec.icon), null)
                    Text(stringResource(shareFileSpec.label), Modifier.padding(start = 4.dp))
                }
            }
        }

        TaskMenu(menu, onAction)
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
private fun TaskFileRow(file: TaskFile) {
    ListItem(
        supportingContent = { Text(fileStatusText(file)) },
        trailingContent = {
            Text(
                text = formatSize(file.size),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        },
    ) { Text(file.path, style = MaterialTheme.typography.bodyMedium, maxLines = 2) }
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
        text = engineText(error),
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

