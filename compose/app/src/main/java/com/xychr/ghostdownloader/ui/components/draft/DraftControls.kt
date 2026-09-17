package com.xychr.ghostdownloader.ui.components.draft

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.packs.DraftControl

@Composable
fun DraftControls(
    controls: List<DraftControl>,
    isEnabled: Boolean,
    onSelect: (id: String, value: String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier.horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        controls.forEach { control -> DraftControlChip(control, isEnabled, onSelect) }
    }
}

@Composable
private fun DraftControlChip(
    control: DraftControl,
    isEnabled: Boolean,
    onSelect: (id: String, value: String) -> Unit,
) {
    var isOpen by remember { mutableStateOf(false) }
    Box {
        FilterChip(
            selected = control.value.isNotEmpty(),
            enabled = isEnabled,
            onClick = { isOpen = true },
            label = { Text(controlLabel(control), maxLines = 1, overflow = TextOverflow.Ellipsis) },
            trailingIcon = {
                Icon(painterResource(R.drawable.ic_arrow_drop_down), null, Modifier.size(18.dp))
            },
            modifier = Modifier.widthIn(max = 200.dp),
        )
        if (!control.isMultiple) DropdownMenu(isOpen, { isOpen = false }) {
            if (control.isOptional) DraftControlEntry(
                label = stringResource(R.string.draft_control_off),
                isSelected = control.value.isEmpty(),
            ) { isOpen = false; onSelect(control.id, "") }
            control.options.forEach { option ->
                DraftControlEntry(option.label, option.key == control.value) {
                    isOpen = false
                    onSelect(control.id, option.key)
                }
            }
        }
    }
    if (control.isMultiple && isOpen) DraftControlSheet(
        control = control,
        onDismiss = { isOpen = false },
        onApply = { isOpen = false; onSelect(control.id, it) },
    )
}

@Composable
private fun DraftControlEntry(label: String, isSelected: Boolean, onClick: () -> Unit) {
    DropdownMenuItem(
        text = { Text(label, maxLines = 1, overflow = TextOverflow.Ellipsis) },
        trailingIcon = {
            if (isSelected) Icon(painterResource(R.drawable.ic_check), null, Modifier.size(18.dp)) else null
        },
        onClick = onClick,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DraftControlSheet(control: DraftControl, onDismiss: () -> Unit, onApply: (String) -> Unit) {
    var selected by remember(control.id) {
        mutableStateOf(control.value.split(",").filter(String::isNotEmpty))
    }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(bottom = 16.dp)) {
            if (control.title.isNotEmpty()) Text(
                control.title,
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
            DraftChoices(control.options, selected, { selected = it },
                Modifier.padding(horizontal = 16.dp))
            Button(
                onClick = { onApply(control.options.filter { it.key in selected }.joinToString(",") { it.key }) },
                enabled = control.isOptional || selected.isNotEmpty(),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            ) {
                Text(stringResource(R.string.draft_apply))
            }
        }
    }
}

@Composable
private fun controlLabel(control: DraftControl): String {
    val keys = control.value.split(",").filter(String::isNotEmpty)
    val valueText = keys.firstOrNull()?.let { key ->
        control.options.firstOrNull { it.key == key }?.label ?: key
    } ?: stringResource(if (control.isMultiple) R.string.draft_control_auto else R.string.draft_control_off)
    return listOf(
        control.title,
        if (keys.size > 1) stringResource(R.string.draft_control_more, valueText, keys.size - 1) else valueText,
    ).filter(String::isNotEmpty).joinToString(" ")
}
