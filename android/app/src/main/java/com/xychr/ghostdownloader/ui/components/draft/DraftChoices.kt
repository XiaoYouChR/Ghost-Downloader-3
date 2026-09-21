package com.xychr.ghostdownloader.ui.components.draft

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.model.DraftOption

@Composable
fun DraftChoices(
    options: List<DraftOption>,
    selected: List<String>,
    onChange: (List<String>) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier) {
        options.forEach { option ->
            val isChecked = option.key in selected
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(isChecked, role = Role.Checkbox,
                onValueChange = { onChange(if (it) selected + option.key else selected - option.key) }),
                verticalAlignment = Alignment.CenterVertically) {
                Checkbox(isChecked, onCheckedChange = null)
                Text(
                    option.label, Modifier.padding(start = 12.dp),
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}
