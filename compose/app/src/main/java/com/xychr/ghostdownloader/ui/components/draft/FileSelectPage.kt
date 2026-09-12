package com.xychr.ghostdownloader.ui.components.draft
import com.xychr.ghostdownloader.model.*

import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.selection.triStateToggleable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.util.formatSize

@Composable
fun FileSelectPage(
    files: List<DraftFile>,
    canRename: Boolean,
    onChange: (List<DraftFile>) -> Unit,
    modifier: Modifier = Modifier,
) {
    var query by rememberSaveable { mutableStateOf("") }
    var renaming by rememberSaveable { mutableStateOf<Int?>(null) }
    val visible = files.filter { it.path.contains(query, ignoreCase = true) }
    val visibleIndexes = visible.map { it.index }.toSet()
    Column(modifier) {
        OutlinedTextField(query, { query = it }, label = { Text(stringResource(R.string.draft_search_files)) },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp), singleLine = true)
        Text(stringResource(R.string.draft_files_selected, files.count { it.isSelected }, files.size),
            Modifier.padding(horizontal = 16.dp))
        Row {
            TextButton(onClick = { onChange(files.map { if (it.index in visibleIndexes) it.copy(isSelected = true) else it }) }) {
                Text(stringResource(R.string.draft_select_all))
            }
            TextButton(onClick = { onChange(files.map { if (it.index in visibleIndexes) it.copy(isSelected = false) else it }) }) {
                Text(stringResource(R.string.draft_deselect_all))
            }
            TextButton(onClick = { onChange(files.map { if (it.index in visibleIndexes) it.copy(isSelected = !it.isSelected) else it }) }) {
                Text(stringResource(R.string.draft_invert))
            }
        }
        LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(bottom = 16.dp)) {
            visible.groupBy { it.path.substringBeforeLast('/', "") }.forEach { (folder, entries) ->
                if (folder.isNotEmpty()) item(key = "folder:$folder") {
                    val selected = entries.count { it.isSelected }
                    val selection = when (selected) {
                        0 -> ToggleableState.Off
                        entries.size -> ToggleableState.On
                        else -> ToggleableState.Indeterminate
                    }
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).triStateToggleable(selection,
                        role = Role.Checkbox, onClick = {
                            val indexes = entries.map { it.index }.toSet()
                            onChange(files.map { if (it.index in indexes) it.copy(isSelected = selected != entries.size) else it })
                        }).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                        TriStateCheckbox(selection, onClick = null)
                        Text(folder, Modifier.padding(start = 12.dp), style = MaterialTheme.typography.titleSmall)
                    }
                }
                items(entries, key = { it.index }) { file ->
                    ListItem(
                        supportingContent = { Text(formatSize(file.size)) },
                        leadingContent = { Checkbox(file.isSelected, onCheckedChange = null) },
                        trailingContent = if (canRename) { {
                            TextButton(onClick = { renaming = if (renaming == file.index) null else file.index }) {
                                Text(stringResource(R.string.draft_rename_file))
                            }
                        } } else null,
                        modifier = Modifier.toggleable(file.isSelected, role = Role.Checkbox,
                            onValueChange = { selected ->
                                onChange(files.map { if (it.index == file.index) it.copy(isSelected = selected) else it })
                            }),
                    ) {
                        if (renaming == file.index) OutlinedTextField(file.path, { value ->
                            onChange(files.map { if (it.index == file.index) it.copy(path = value) else it })
                        }, singleLine = true, label = { Text(stringResource(R.string.draft_name)) })
                        else Text(file.path)
                    }
                }
            }
        }
    }
}
