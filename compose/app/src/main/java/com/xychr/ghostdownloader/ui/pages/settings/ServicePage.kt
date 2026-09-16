package com.xychr.ghostdownloader.ui.pages.settings

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Environment
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.Settings
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.InfoSettingRow
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.NumberSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.engine.SettingRanges
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import java.io.File

@Composable
fun ServicePage(onBack: () -> Unit, viewModel: SettingsViewModel) {
    val settings by viewModel.settings.collectAsStateWithLifecycle()

    SettingsScaffold(stringResource(R.string.settings_section_local_service), onBack) {
        settings?.let { ServiceRows(it, viewModel::set) } ?: LoadingRow()
    }
}

@Composable
private fun ColumnScope.ServiceRows(settings: Settings, set: (String, Any) -> Unit) {
    SettingSection(title = stringResource(R.string.settings_browser_extension)) {
        SwitchSettingRow(
            title = stringResource(R.string.settings_browser_extension),
            subtitle = stringResource(R.string.settings_browser_extension_desc),
            checked = settings.isBrowserExtensionEnabled,
            onCheckedChange = {
                set("isBrowserExtensionEnabled", it)
            },
        )
        BrowserExtensionRows(
            isEnabled = settings.isBrowserExtensionEnabled,
            port = settings.browserExtensionPort,
            set = set,
        )
        if (settings.isBrowserExtensionEnabled) {
            SwitchSettingRow(
                title = stringResource(R.string.settings_taken_draft),
                subtitle = stringResource(R.string.settings_taken_draft_desc),
                checked = settings.shouldDraftTakenDownload,
                onCheckedChange = { set("shouldDraftTakenDownload", it) },
            )
        }
    }

    SettingSection(title = stringResource(R.string.settings_aria2_rpc)) {
        SwitchSettingRow(
            title = stringResource(R.string.settings_aria2_rpc),
            subtitle = stringResource(R.string.settings_aria2_rpc_desc),
            checked = settings.isAria2RpcEnabled,
            onCheckedChange = {
                set("isAria2RpcEnabled", it)
            },
        )
        if (settings.isAria2RpcEnabled) {
            NumberSettingRow(
                title = stringResource(R.string.settings_aria2_rpc_port),
                value = settings.aria2RpcPort,
                range = SettingRanges["aria2RpcPort"],
                onConfirm = { set("aria2RpcPort", it) },
            )
            TextSettingRow(
                title = stringResource(R.string.settings_aria2_rpc_token),
                value = settings.aria2RpcToken,
                onConfirm = { set("aria2RpcToken", it) },
                emptyHint = stringResource(R.string.settings_aria2_rpc_token_desc),
            )
            SwitchSettingRow(
                title = stringResource(R.string.settings_aria2_rpc_emulate),
                subtitle = stringResource(R.string.settings_aria2_rpc_emulate_desc),
                checked = settings.aria2RpcEmulateFingerprint,
                onCheckedChange = { set("aria2RpcEmulateFingerprint", it) },
            )
        }
    }
}

@Serializable
data class BrowserExtension(
    val port: Int = 0,
    val token: String = "",
    val installType: String = "",
    val extensionVersion: String = "",
)

@Composable
private fun BrowserExtensionRows(isEnabled: Boolean, port: Int, set: (String, Any) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf(BrowserExtension()) }

    LaunchedEffect(isEnabled) {
        while (isEnabled) {
            state = runCatching { engineRepository.query<BrowserExtension>("browserExtension") }
                .getOrDefault(BrowserExtension())
            delay(2000)
        }
    }

    if (!isEnabled) return

    NumberSettingRow(
        title = stringResource(R.string.settings_browser_port),
        value = port,
        range = SettingRanges["browserExtensionPort"],
        onConfirm = { set("browserExtensionPort", it) },
    )
    ActionSettingRow(
        title = stringResource(R.string.settings_browser_token),
        subtitle = state.token,
        onClick = { context.copyToClipboard(state.token) },
    )
    InfoSettingRow(
        title = stringResource(R.string.settings_browser_status),
        subtitle = if (state.installType.isEmpty())
            stringResource(R.string.settings_browser_disconnected)
        else stringResource(R.string.settings_browser_connected, state.extensionVersion),
    )
    var exported by remember { mutableStateOf("") }
    ActionSettingRow(
        title = stringResource(R.string.settings_browser_export),
        subtitle = exported.ifEmpty { stringResource(R.string.settings_browser_export_desc) },
        onClick = {
            scope.launch {
                exported = exportBrowserExtension(context)
            }
        },
    )
    ActionSettingRow(
        title = stringResource(R.string.settings_browser_regenerate),
        subtitle = stringResource(R.string.settings_browser_regenerate_desc),
        onClick = {
            scope.launch {
                runCatching {
                    engineRepository.invoke("regenerateBrowserToken")
                    state = engineRepository.query("browserExtension")
                }
            }
        },
    )
}

private suspend fun exportBrowserExtension(context: Context): String = withContext(Dispatchers.IO) {
    runCatching {
        val crx = File(context.cacheDir, "chrome_extension.crx")
        context.assets.open("chrome_extension.crx").use { input ->
            crx.outputStream().use(input::copyTo)
        }
        val folder = File(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
            "GhostDownloaderExtension",
        )
        engineRepository.invoke("extractBrowserExtension", crx.absolutePath, folder.absolutePath)
        folder.absolutePath
    }.getOrElse { it.message ?: "" }
}

private fun Context.copyToClipboard(text: String) {
    getSystemService(ClipboardManager::class.java)
        .setPrimaryClip(ClipData.newPlainText("token", text))
}
