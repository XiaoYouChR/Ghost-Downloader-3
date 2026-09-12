package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.Saver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.Settings
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsEdit
import com.xychr.ghostdownloader.ui.components.settings.SettingsEditState
import com.xychr.ghostdownloader.ui.components.settings.SettingsEditor
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.ui.navigation.ProxySettingsRoute
import com.xychr.ghostdownloader.ui.navigation.Route
import java.net.URI
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

// --- Proxy model ---

enum class ProxyMode { OFF, AUTO, CUSTOM }

@Serializable
data class ProxyInput(
    val mode: ProxyMode = ProxyMode.AUTO,
    val protocol: String = "http",
    val host: String = "",
    val port: String = "",
    val username: String = "",
    val password: String = "",
)

fun parseProxy(value: String): ProxyInput {
    if (value == "Auto") return ProxyInput()
    if (value == "Off") return ProxyInput(mode = ProxyMode.OFF)
    val uri = runCatching { URI(value) }.getOrNull()
    val credentials = uri?.rawUserInfo.orEmpty()
    return ProxyInput(
        mode = ProxyMode.CUSTOM, protocol = uri?.scheme ?: "http",
        host = uri?.host ?: value, port = uri?.port?.takeIf { it >= 0 }?.toString().orEmpty(),
        username = credentials.substringBefore(':'), password = credentials.substringAfter(':', ""),
    )
}

fun buildProxy(input: ProxyInput): String = when (input.mode) {
    ProxyMode.OFF -> "Off"
    ProxyMode.AUTO -> "Auto"
    ProxyMode.CUSTOM -> buildString {
        append(input.protocol).append("://")
        if (input.username.isNotEmpty() || input.password.isNotEmpty()) {
            append(input.username).append(':').append(input.password).append('@')
        }
        append(input.host.trim()).append(':').append(input.port)
    }
}

fun matchProxyHost(host: String): Boolean {
    val value = host.trim()
    if (Regex("[0-9.]+").matches(value)) {
        val parts = value.split('.')
        return parts.size == 4 && parts.all { it.toIntOrNull() in 0..255 && it.length <= 3 }
    }
    // 与现有 Engine ProxyValidator 支持的域名范围一致，不向用户承诺它不能保存的格式。
    return Regex("(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\\.)+[a-zA-Z]{2,6}").matches(value)
}

fun matchProxy(input: ProxyInput): Boolean = input.mode != ProxyMode.CUSTOM || (
    input.protocol in listOf("http", "https", "socks4", "socks5", "socks5h") &&
    matchProxyHost(input.host) && input.port.toIntOrNull() in 1..65535 &&
    matchProxyCredentials(input)
)

fun matchProxyCredentials(input: ProxyInput): Boolean =
    (input.username.isEmpty() && input.password.isEmpty()) ||
        (Regex("[\\p{L}\\p{N}_]+").matches(input.username) &&
            Regex("[\\p{L}\\p{N}_!@#$%^&*()]+").matches(input.password))

// --- Network page ---

@Composable
fun NetworkPage(onNavigate: (Route) -> Unit, onBack: () -> Unit, viewModel: SettingsViewModel) {
    val settings by viewModel.settings.collectAsStateWithLifecycle()

    SettingsPage(stringResource(R.string.settings_section_network), onBack) {
        settings?.let { NetworkRows(it, viewModel::set, { onNavigate(ProxySettingsRoute) }) } ?: LoadingRow()
    }
}

@Composable
private fun ColumnScope.NetworkRows(settings: Settings, set: (String, Any) -> Unit, onProxy: () -> Unit) {
    SettingSection {
        SwitchSettingRow(
            title = stringResource(R.string.settings_system_dns),
            subtitle = stringResource(R.string.settings_system_dns_desc),
            checked = settings.shouldUseSystemDns,
            onCheckedChange = { set("shouldUseSystemDns", it) },
        )
        ActionSettingRow(
            title = stringResource(R.string.settings_proxy),
            subtitle = proxySummary(settings.proxyServer),
            onClick = onProxy,
        )
        SwitchSettingRow(
            title = stringResource(R.string.settings_verify_ssl),
            checked = settings.shouldVerifySsl,
            onCheckedChange = { set("shouldVerifySsl", it) },
        )
    }
}

// --- Proxy page ---

@Composable
fun ProxyPage(onBack: () -> Unit, viewModel: SettingsViewModel, modifier: Modifier = Modifier, edit: SettingsEdit = viewModel()) {
    val settings by viewModel.settings.collectAsStateWithLifecycle()
    val editState by edit.state.collectAsStateWithLifecycle()
    val proxyServer = settings?.proxyServer
    if (proxyServer == null) {
        SettingsPage(stringResource(R.string.proxy_edit), onBack, modifier) { LoadingRow() }
    } else {
        ProxyForm(proxyServer, editState,
            onSave = { proxy -> edit.save { EngineRepository.invoke("setSetting", "proxyServer", proxy) } },
            onBack = onBack, modifier = modifier)
    }
}

@Composable
fun ProxyForm(initial: String, state: SettingsEditState, onSave: (String) -> Unit, onBack: () -> Unit,
    modifier: Modifier = Modifier) {
    var input by rememberSaveable(stateSaver = Saver<ProxyInput, String>(
        save = { Json.encodeToString(ProxyInput.serializer(), it) },
        restore = { Json.decodeFromString(ProxyInput.serializer(), it) },
    )) { mutableStateOf(parseProxy(initial)) }
    var shouldValidate by rememberSaveable { mutableStateOf(false) }
    var isAuthExpanded by rememberSaveable { mutableStateOf(input.username.isNotEmpty() || input.password.isNotEmpty()) }
    var isPasswordVisible by remember { mutableStateOf(false) }
    var shouldFocusAuth by remember { mutableStateOf(false) }
    val hostFocus = remember { FocusRequester() }
    val portFocus = remember { FocusRequester() }
    val userFocus = remember { FocusRequester() }
    val isCustom = input.mode == ProxyMode.CUSTOM
    SettingsEditor(stringResource(R.string.proxy_edit), state, input != parseProxy(initial), matchProxy(input),
        onSave = { onSave(buildProxy(input)) }, onBack = onBack, modifier = modifier,
        onInvalid = {
            shouldValidate = true
            when {
                !matchProxyHost(input.host) -> hostFocus.requestFocus()
                input.port.toIntOrNull() !in 1..65535 -> portFocus.requestFocus()
                else -> { isAuthExpanded = true; shouldFocusAuth = true }
            }
        }) {
        Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            ChoiceField(stringResource(R.string.settings_proxy), input.mode.name,
                listOf(ProxyMode.OFF.name to stringResource(R.string.proxy_off),
                    ProxyMode.AUTO.name to stringResource(R.string.proxy_auto),
                    ProxyMode.CUSTOM.name to stringResource(R.string.proxy_custom)),
                { input = input.copy(mode = ProxyMode.valueOf(it)) }, isEnabled = !state.isSaving)
            Text(stringResource(R.string.proxy_save_hint), style = MaterialTheme.typography.bodySmall)
            if (isCustom) {
                ChoiceField(stringResource(R.string.proxy_protocol), input.protocol,
                    listOf("http", "https", "socks4", "socks5", "socks5h").map { it to it.uppercase() },
                    { input = input.copy(protocol = it) }, isEnabled = !state.isSaving)
                OutlinedTextField(input.host, { input = input.copy(host = it) }, singleLine = true,
                    enabled = !state.isSaving, label = { Text(stringResource(R.string.proxy_host)) },
                    isError = shouldValidate && !matchProxyHost(input.host),
                    supportingText = { Text(stringResource(if (shouldValidate && !matchProxyHost(input.host))
                        R.string.proxy_host_invalid else R.string.proxy_host_help)) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, autoCorrectEnabled = false),
                    modifier = Modifier.fillMaxWidth().focusRequester(hostFocus))
                OutlinedTextField(input.port, { input = input.copy(port = it) }, singleLine = true,
                    enabled = !state.isSaving, label = { Text(stringResource(R.string.proxy_port)) },
                    isError = shouldValidate && input.port.toIntOrNull() !in 1..65535,
                    supportingText = { if (shouldValidate && input.port.toIntOrNull() !in 1..65535)
                        Text(stringResource(R.string.proxy_port_invalid)) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth().focusRequester(portFocus))
                TextButton(onClick = { isAuthExpanded = !isAuthExpanded }, enabled = !state.isSaving) {
                    Text(stringResource(R.string.proxy_auth))
                }
                if (isAuthExpanded) {
                    LaunchedEffect(shouldFocusAuth) {
                        if (shouldFocusAuth) { userFocus.requestFocus(); shouldFocusAuth = false }
                    }
                    OutlinedTextField(input.username, { input = input.copy(username = it) }, singleLine = true,
                        label = { Text(stringResource(R.string.proxy_username)) }, enabled = !state.isSaving,
                        keyboardOptions = KeyboardOptions(autoCorrectEnabled = false),
                        modifier = Modifier.fillMaxWidth().focusRequester(userFocus))
                    OutlinedTextField(input.password, { input = input.copy(password = it) }, singleLine = true,
                        label = { Text(stringResource(R.string.proxy_password)) }, enabled = !state.isSaving,
                        visualTransformation = if (isPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                        isError = shouldValidate && !matchProxyCredentials(input),
                        supportingText = { if (shouldValidate && !matchProxyCredentials(input)) Text(stringResource(R.string.proxy_auth_invalid)) },
                        modifier = Modifier.fillMaxWidth())
                    TextButton(onClick = { isPasswordVisible = !isPasswordVisible }) {
                        Text(stringResource(if (isPasswordVisible) R.string.proxy_hide_password else R.string.proxy_show_password))
                    }
                }
            }
        }
    }
}

@Composable
fun proxySummary(value: String): String {
    val proxy = parseProxy(value)
    return when (proxy.mode) {
        ProxyMode.AUTO -> stringResource(R.string.proxy_auto)
        ProxyMode.OFF -> stringResource(R.string.proxy_off)
        ProxyMode.CUSTOM -> stringResource(R.string.proxy_summary_custom, proxy.protocol.uppercase(),
            proxy.host.substringAfterLast('@'), proxy.port)
    }
}
