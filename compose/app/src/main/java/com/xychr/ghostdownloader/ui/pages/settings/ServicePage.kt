package com.xychr.ghostdownloader.ui.pages.settings

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Environment
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.Settings
import com.xychr.ghostdownloader.ui.components.notice.LocalSnackbar
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.ConfirmDialog
import com.xychr.ghostdownloader.ui.components.settings.InfoSettingRow
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.NumberSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.engine.SettingRanges
import com.xychr.ghostdownloader.ui.platform.openUrl
import kotlinx.coroutines.Dispatchers
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
                isSecret = true,
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
private data class BrowserExtension(
    val status: String = "",
    val token: String = "",
    val extensionVersion: String = "",
    val chromeWebstore: String = "",
    val edgeAddons: String = "",
    val firefoxAddons: String = "",
)

@Composable
private fun BrowserExtensionRows(isEnabled: Boolean, port: Int, set: (String, Any) -> Unit) {
    if (!isEnabled) return

    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val state by remember { engineRepository.observe<BrowserExtension>("browserExtension") }
        .collectAsStateWithLifecycle(BrowserExtension())
    var exported by remember { mutableStateOf("") }

    NumberSettingRow(
        title = stringResource(R.string.settings_browser_port),
        value = port,
        range = SettingRanges["browserExtensionPort"],
        onConfirm = { set("browserExtensionPort", it) },
    )
    InfoSettingRow(
        title = stringResource(R.string.settings_browser_status),
        subtitle = when (state.status) {
            "connected" -> stringResource(R.string.settings_browser_connected, state.extensionVersion)
            "listening" -> stringResource(R.string.settings_browser_listening, port)
            "portUnavailable" -> stringResource(R.string.settings_browser_port_unavailable, port)
            else -> stringResource(R.string.settings_browser_disconnected)
        },
    )
    CopyTokenRow(state.token)
    RegenerateTokenRow()
    ActionSettingRow(
        title = stringResource(R.string.settings_browser_export),
        subtitle = exported.ifEmpty { stringResource(R.string.settings_browser_export_desc) },
        onClick = { scope.launch { exported = exportBrowserExtension(context) } },
    )
    ActionSettingRow(
        title = stringResource(R.string.settings_browser_store_chrome),
        onClick = { context.openUrl(state.chromeWebstore) },
    )
    ActionSettingRow(
        title = stringResource(R.string.settings_browser_store_edge),
        onClick = { context.openUrl(state.edgeAddons) },
    )
    ActionSettingRow(
        title = stringResource(R.string.settings_browser_store_firefox),
        onClick = { context.openUrl(state.firefoxAddons) },
    )
}

@Composable
private fun CopyTokenRow(token: String) {
    val context = LocalContext.current
    val snackbar = LocalSnackbar.current
    val scope = rememberCoroutineScope()

    ActionSettingRow(
        title = stringResource(R.string.settings_browser_token),
        subtitle = token,
        trailing = {
            Icon(
                painterResource(R.drawable.ic_copy),
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        },
        onClick = {
            context.copyToClipboard(token)
            scope.launch {
                snackbar.showSnackbar(context.getString(R.string.settings_browser_token_copied))
            }
        },
    )
}

@Composable
private fun RegenerateTokenRow() {
    val scope = rememberCoroutineScope()
    var isConfirming by remember { mutableStateOf(false) }

    ActionSettingRow(
        title = stringResource(R.string.settings_browser_regenerate),
        subtitle = stringResource(R.string.settings_browser_regenerate_desc),
        onClick = { isConfirming = true },
    )

    if (isConfirming) {
        ConfirmDialog(
            title = stringResource(R.string.settings_browser_regenerate),
            message = stringResource(R.string.settings_browser_regenerate_confirm),
            onDismiss = { isConfirming = false },
            onConfirm = { scope.launch { engineRepository.invoke("regenerateBrowserToken") } },
        )
    }
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
