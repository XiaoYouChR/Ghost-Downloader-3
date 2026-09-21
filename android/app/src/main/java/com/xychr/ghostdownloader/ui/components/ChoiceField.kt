package com.xychr.ghostdownloader.ui.components

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuAnchorType
import androidx.compose.material3.ExposedDropdownMenu
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChoiceField(
    label: String,
    value: String,
    options: List<Pair<String, String>>,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
    isEnabled: Boolean = true,
    isError: Boolean = false,
    supportingText: (@Composable () -> Unit)? = null,
) {
    var isExpanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(isExpanded && isEnabled, { if (isEnabled) isExpanded = it }, modifier) {
        OutlinedTextField(
            value = options.firstOrNull { it.first == value }?.second ?: value,
            onValueChange = {}, readOnly = true, enabled = isEnabled, label = { Text(label) },
            isError = isError, supportingText = supportingText,
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(isExpanded) },
            modifier = Modifier.menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable, enabled = isEnabled).fillMaxWidth(),
        )
        ExposedDropdownMenu(isExpanded && isEnabled, { isExpanded = false }) {
            options.forEach { (key, text) ->
                DropdownMenuItem(text = { Text(text) }, onClick = { isExpanded = false; onSelect(key) })
            }
        }
    }
}
