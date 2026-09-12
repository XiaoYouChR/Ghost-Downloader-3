package com.xychr.ghostdownloader.ui.components.settings

import android.view.HapticFeedbackConstants
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.toggleableState
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import kotlin.math.roundToInt

@Composable
fun SettingsSectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.primary,
        modifier = modifier.padding(horizontal = 16.dp, vertical = 8.dp).semantics { heading() },
    )
}

// 外层裁剪只限定整组轮廓，行自己绘制底色与按压形变，动态增删行无需维护位置参数。
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun SettingSection(
    modifier: Modifier = Modifier,
    title: String? = null,
    description: String? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        if (title != null) SettingsSectionTitle(title)
        if (description != null) {
            Text(
                text = description,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 12.dp),
            )
        }
        Column(
            modifier = Modifier.fillMaxWidth().clip(MaterialTheme.shapes.largeIncreased),
            verticalArrangement = Arrangement.spacedBy(2.dp),
            content = content,
        )
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun SwitchSettingRow(
    title: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
) {
    val view = LocalView.current
    ListItem(
        content = { Text(title) },
        supportingContent = subtitle?.let { { Text(it) } },
        trailingContent = { Switch(checked = checked, onCheckedChange = null) },
        shapes = ListItemDefaults.shapes(pressedShape = MaterialTheme.shapes.extraLarge),
        colors = ListItemDefaults.segmentedColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        // ListItem 的 checked 重载固定为 Checkbox；这里保留整行 Switch 的单一语义节点。
        modifier = modifier.semantics {
            role = Role.Switch
            toggleableState = ToggleableState(checked)
        },
        onClick = {
            view.performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK)
            onCheckedChange(!checked)
        },
    )
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun ActionSettingRow(
    title: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    leading: (@Composable () -> Unit)? = null,
    trailing: (@Composable () -> Unit)? = null,
) {
    val view = LocalView.current
    ListItem(
        content = { Text(title) },
        supportingContent = subtitle?.let { { Text(it) } },
        leadingContent = leading,
        trailingContent = trailing,
        shapes = ListItemDefaults.shapes(pressedShape = MaterialTheme.shapes.extraLarge),
        colors = ListItemDefaults.segmentedColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        modifier = modifier,
        onClick = {
            view.performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK)
            onClick()
        },
    )
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun InfoSettingRow(
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    trailing: (@Composable () -> Unit)? = null,
) {
    ListItem(
        content = { Text(title) },
        supportingContent = subtitle?.let { { Text(it) } },
        trailingContent = trailing,
        colors = ListItemDefaults.segmentedColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        modifier = modifier,
    )
}

/**
 * 拖动只改本地值，抬手才提交——引擎每次 set 都会写盘。
 * remember 以外部值为 key，外部变化能覆盖本地值。
 */
@Composable
fun SliderSettingRow(
    title: String,
    value: Int,
    range: IntRange,
    valueText: (Int) -> String,
    onCommit: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    var dragging by remember(value) { mutableFloatStateOf(value.toFloat()) }
    val span = range.last - range.first

    Column(
        modifier.fillMaxWidth()
            .clip(MaterialTheme.shapes.extraSmall)
            .background(MaterialTheme.colorScheme.surfaceContainerLow)
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(title, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
            Text(
                text = valueText(dragging.roundToInt()),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Slider(
            value = dragging,
            modifier = Modifier.semantics {
                contentDescription = title
                stateDescription = valueText(dragging.roundToInt())
            },
            onValueChange = { dragging = it },
            onValueChangeFinished = { onCommit(dragging.roundToInt()) },
            valueRange = range.first.toFloat()..range.last.toFloat(),
            steps = if (span <= 20) span - 1 else 0,
        )
    }
}

@Composable
fun RadioRow(text: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .selectable(selected = selected, role = Role.RadioButton, onClick = onClick)
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = null)
        Text(text, modifier = Modifier.padding(start = 8.dp))
    }
}


// 引擎决定合法范围，这里只挡住明显越界。
@Composable
fun NumberSettingRow(
    title: String,
    value: Int,
    range: IntRange,
    onConfirm: (Int) -> Unit,
    unit: String = "",
    valueText: (Int) -> String = { if (unit.isEmpty()) "$it" else "$it $unit" },
) {
    var editing by remember { mutableStateOf(false) }

    ActionSettingRow(title = title, subtitle = valueText(value), onClick = { editing = true })

    if (editing) {
        var text by remember { mutableStateOf(value.toString()) }
        val entered = text.toIntOrNull()
        AlertDialog(
            onDismissRequest = { editing = false },
            title = { Text(title) },
            text = {
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it.filter { c -> c.isDigit() || c == '-' }.take(9) },
                    suffix = unit.takeIf(String::isNotEmpty)?.let { { Text(it) } },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        onConfirm(entered!!)
                        editing = false
                    },
                    enabled = entered != null && entered in range,
                ) { Text(stringResource(R.string.action_ok)) }
            },
            dismissButton = {
                TextButton(onClick = { editing = false }) {
                    Text(stringResource(R.string.action_cancel))
                }
            },
        )
    }
}

// 空值时用 emptyHint 代替副标题。
@Composable
fun TextSettingRow(
    title: String,
    value: String,
    onConfirm: (String) -> Unit,
    emptyHint: String = "",
    placeholder: String = "",
    singleLine: Boolean = true,
) {
    var editing by remember { mutableStateOf(false) }

    ActionSettingRow(
        title = title,
        subtitle = value.ifEmpty { emptyHint },
        onClick = { editing = true },
    )

    if (editing) {
        var text by remember { mutableStateOf(value) }
        AlertDialog(
            onDismissRequest = { editing = false },
            title = { Text(title) },
            text = {
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    placeholder = placeholder.takeIf(String::isNotEmpty)?.let { { Text(it) } },
                    singleLine = singleLine,
                    minLines = if (singleLine) 1 else 4,
                    modifier = Modifier.fillMaxWidth(),
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    onConfirm(text.trim())
                    editing = false
                }) { Text(stringResource(R.string.action_ok)) }
            },
            dismissButton = {
                TextButton(onClick = { editing = false }) {
                    Text(stringResource(R.string.action_cancel))
                }
            },
        )
    }
}

// options: 引擎值 to 展示文案。
@Composable
fun OptionsSettingRow(
    title: String,
    value: String,
    options: List<Pair<String, String>>,
    onSelect: (String) -> Unit,
    leading: (@Composable () -> Unit)? = null,
    isEnabled: Boolean = true,
) {
    var picking by remember { mutableStateOf(false) }

    ActionSettingRow(
        title = title,
        subtitle = options.firstOrNull { it.first == value }?.second ?: value,
        leading = leading,
        onClick = { if (isEnabled) picking = true },
    )

    if (picking) {
        AlertDialog(
            onDismissRequest = { picking = false },
            title = { Text(title) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState()).selectableGroup()) {
                    options.forEach { (option, label) ->
                        RadioRow(label, option == value) {
                            onSelect(option)
                            picking = false
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { picking = false }) {
                    Text(stringResource(R.string.action_cancel))
                }
            },
        )
    }
}
