package com.xychr.ghostdownloader.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.util.formatSize

private const val INDENT_STEP = 16

data class SelectableFile(val index: Int, val path: String, val groups: List<String>, val size: Long)

internal sealed interface TreeRow {
    val depth: Int
}

internal data class FolderRow(
    override val depth: Int,
    val key: List<String>,
    val descendants: List<Int>,
) : TreeRow

internal data class FileRow(override val depth: Int, val file: SelectableFile) : TreeRow

private fun toKeys(groups: List<String>): List<List<String>> = groups.indices.map { groups.take(it + 1) }

internal fun buildCollapsed(files: List<SelectableFile>, selected: Set<Int>): Set<List<String>> {
    val chosen = files.filter { it.index in selected }
    if (chosen.isEmpty() || chosen.size == files.size) return emptySet()
    return files.flatMap { toKeys(it.groups) }.toSet() - chosen.flatMap { toKeys(it.groups) }.toSet()
}

internal fun buildRows(files: List<SelectableFile>, collapsed: Set<List<String>>): List<TreeRow> {
    val entries = files.map { it to toKeys(it.groups) }
    val descendants = mutableMapOf<List<String>, MutableList<Int>>()
    entries.forEach { (file, keys) ->
        keys.forEach { descendants.getOrPut(it) { mutableListOf() }.add(file.index) }
    }

    val rows = mutableListOf<TreeRow>()
    var previous = emptyList<List<String>>()
    entries.sortedBy { it.first.path }.forEach { (file, keys) ->
        val collapsedDepth = keys.indexOfFirst { it in collapsed }
        keys.forEachIndexed { depth, key ->
            if (collapsedDepth in 0..<depth) return@forEachIndexed
            if (depth >= previous.size || previous[depth] != key) {
                rows += FolderRow(depth, key, descendants[key].orEmpty())
            }
        }
        previous = keys
        if (collapsedDepth < 0) rows += FileRow(keys.size, file)
    }
    return rows
}

@Composable
fun SelectableFileList(
    files: List<SelectableFile>,
    selectedIndexes: Set<Int>,
    onSelectionChange: (Set<Int>) -> Unit,
    modifier: Modifier = Modifier,
    isEnabled: Boolean = true,
    onRename: ((index: Int, newPath: String) -> Unit)? = null,
) {
    var query by rememberSaveable { mutableStateOf("") }
    var renaming by rememberSaveable { mutableStateOf<Int?>(null) }
    var collapsed by rememberSaveable { mutableStateOf(buildCollapsed(files, selectedIndexes)) }

    val visible = remember(files, query) { files.filter { it.path.contains(query, ignoreCase = true) } }
    val visibleIndexes = remember(visible) { visible.map { it.index }.toSet() }
    val isSearching = query.isNotEmpty()
    val canToggleCollapse = !isSearching
    val collapsedNow = if (canToggleCollapse) collapsed else emptySet<List<String>>()
    val rows = remember(visible, collapsedNow) { buildRows(visible, collapsedNow) }
    val topKeys = remember(files) { files.mapNotNull { it.groups.firstOrNull()?.let { one -> listOf(one) } }.toSet() }

    Column(modifier) {
        OutlinedTextField(
            query, { query = it }, label = { Text(stringResource(R.string.file_select_search)) },
            leadingIcon = { Icon(painterResource(R.drawable.ic_search), null) },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp), singleLine = true,
        )
        Row(Modifier.padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { onSelectionChange(selectedIndexes + visibleIndexes) }, enabled = isEnabled) {
                Text(stringResource(R.string.file_select_all))
            }
            TextButton(onClick = { onSelectionChange(selectedIndexes - visibleIndexes) }, enabled = isEnabled) {
                Text(stringResource(R.string.file_select_none))
            }
            TextButton(onClick = {
                val turnedOn = visibleIndexes.filterNot { it in selectedIndexes }.toSet()
                onSelectionChange(selectedIndexes - visibleIndexes + turnedOn)
            }, enabled = isEnabled) {
                Text(stringResource(R.string.file_select_invert))
            }
            Spacer(Modifier.weight(1f))
            IconButton(onClick = { collapsed = emptySet() }, enabled = isEnabled && canToggleCollapse) {
                Icon(painterResource(R.drawable.ic_folder_open), stringResource(R.string.file_select_expand_all))
            }
            IconButton(onClick = { collapsed = topKeys }, enabled = isEnabled && canToggleCollapse) {
                Icon(painterResource(R.drawable.ic_folder), stringResource(R.string.file_select_collapse_all))
            }
        }
        LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(bottom = 16.dp)) {
            items(
                rows,
                key = { row ->
                    when (row) {
                        is FolderRow -> "d:${row.key}"
                        is FileRow -> "f:${row.file.index}"
                    }
                },
            ) { row ->
                when (row) {
                    is FolderRow -> {
                        val onExpand: (() -> Unit)? = if (canToggleCollapse) {
                            { collapsed = if (row.key in collapsed) collapsed - setOf(row.key) else collapsed + setOf(row.key) }
                        } else null
                        FolderItem(
                            row = row,
                            isExpanded = row.key !in collapsedNow,
                            selectedCount = row.descendants.count { it in selectedIndexes },
                            isEnabled = isEnabled,
                            onToggleExpand = onExpand,
                            onToggleSelect = { isOn ->
                                onSelectionChange(
                                    if (isOn) selectedIndexes + row.descendants else selectedIndexes - row.descendants
                                )
                            },
                        )
                    }

                    is FileRow -> {
                        val file = row.file
                        val rename = onRename
                        FileItem(
                            file = file,
                            depth = row.depth,
                            isSelected = file.index in selectedIndexes,
                            isRenaming = renaming == file.index,
                            isEnabled = isEnabled,
                            onToggleRename = { renaming = if (renaming == file.index) null else file.index },
                            onSelect = { isOn ->
                                onSelectionChange(
                                    if (isOn) selectedIndexes + file.index else selectedIndexes - file.index
                                )
                            },
                            onRenamePath = rename?.let { callback -> { path -> callback(file.index, path) } },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun FolderItem(
    row: FolderRow,
    isExpanded: Boolean,
    selectedCount: Int,
    isEnabled: Boolean,
    onToggleExpand: (() -> Unit)?,
    onToggleSelect: (Boolean) -> Unit,
) {
    val selection = when (selectedCount) {
        0 -> ToggleableState.Off
        row.descendants.size -> ToggleableState.On
        else -> ToggleableState.Indeterminate
    }
    ListItem(
        supportingContent = { Text("$selectedCount/${row.descendants.size}") },
        leadingContent = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Spacer(Modifier.width((row.depth * INDENT_STEP).dp))
                TriStateCheckbox(
                    selection,
                    onClick = { onToggleSelect(selection != ToggleableState.On) },
                    enabled = isEnabled,
                )
                Icon(painterResource(R.drawable.ic_folder), null, Modifier.padding(start = 4.dp).size(20.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        trailingContent = {
            Icon(painterResource(R.drawable.ic_chevron_right), null,
                Modifier.size(20.dp).graphicsLayer { rotationZ = if (isExpanded) 90f else 0f },
                tint = MaterialTheme.colorScheme.onSurfaceVariant)
        },
        modifier = if (onToggleExpand == null) Modifier else Modifier.clickable(
            enabled = isEnabled,
            onClickLabel = stringResource(if (isExpanded) R.string.file_select_collapse else R.string.file_select_expand),
            onClick = onToggleExpand,
        ),
    ) {
        Text(row.key.last(), style = MaterialTheme.typography.titleSmall,
            maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun FileItem(
    file: SelectableFile,
    depth: Int,
    isSelected: Boolean,
    isRenaming: Boolean,
    isEnabled: Boolean,
    onToggleRename: () -> Unit,
    onSelect: (Boolean) -> Unit,
    onRenamePath: ((String) -> Unit)?,
) {
    ListItem(
        supportingContent = { Text(formatSize(file.size)) },
        leadingContent = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Spacer(Modifier.width((depth * INDENT_STEP).dp))
                Checkbox(isSelected, onCheckedChange = null, enabled = isEnabled)
            }
        },
        trailingContent = if (onRenamePath != null) {
            {
                IconButton(onClick = onToggleRename, enabled = isEnabled) {
                    Icon(painterResource(R.drawable.ic_edit), stringResource(R.string.file_rename))
                }
            }
        } else null,
        modifier = if (isRenaming) Modifier else Modifier.toggleable(
            isSelected, enabled = isEnabled, role = Role.Checkbox, onValueChange = onSelect,
        ),
    ) {
        if (isRenaming) OutlinedTextField(
            file.path.substringAfterLast('/'),
            { name -> onRenamePath?.invoke(
                file.path.substringBeforeLast('/', "").let { if (it.isEmpty()) name else "$it/$name" }
            ) },
            singleLine = true, label = { Text(stringResource(R.string.file_name)) },
            modifier = Modifier.fillMaxWidth(),
        ) else Text(file.path.substringAfterLast('/'), maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}
