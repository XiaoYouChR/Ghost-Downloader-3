package com.xychr.ghostdownloader.features.bili_pack

import com.xychr.ghostdownloader.packs.*

import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.MultiFormatWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable

@Serializable
data class BiliAccount(
    val isLoggedIn: Boolean = false,
    val username: String = "",
    val mid: String = "",
    val vip: String = "",
    val cookie: String = "",
)

@Serializable
data class BiliQr(
    val status: String = "loading",
    val url: String = "",
    val message: String = "",
)

class BilibiliAccountViewModel(
    private val send: suspend (String, List<Any>) -> Unit,
    accountFlow: Flow<BiliAccount>,
    qrFlow: Flow<BiliQr>,
) : ViewModel() {

    val account: StateFlow<BiliAccount> =
        accountFlow.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), BiliAccount())

    val qr: StateFlow<BiliQr> =
        qrFlow.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), BiliQr())

    fun startQrLogin() {
        viewModelScope.launch { send("startQrLogin", emptyList()) }
    }

    fun cancelQrLogin() {
        viewModelScope.launch { send("cancelQrLogin", emptyList()) }
    }

    fun setCookie(cookie: String) {
        viewModelScope.launch { send("setCookie", listOf(cookie)) }
    }

    fun logout() {
        viewModelScope.launch { send("logout", emptyList()) }
    }
}

@Composable
fun BilibiliLoginRows(
    viewModel: BilibiliAccountViewModel = viewModel {
        val packId = BilibiliUi.packId
        BilibiliAccountViewModel(
            send = { action, args ->
                EngineRepository.invoke("requestPack", packId, action, *args.toTypedArray())
            },
            accountFlow = EngineRepository.observe("pack:$packId:accountState"),
            qrFlow = EngineRepository.observe("pack:$packId:qrState"),
        )
    },
) {
    val account by viewModel.account.collectAsStateWithLifecycle()
    var isScanning by remember { mutableStateOf(false) }
    var isEditingCookie by remember { mutableStateOf(false) }

    SettingSection {
        ActionSettingRow(
            title = stringResource(R.string.bili_scan_login),
            subtitle = if (account.isLoggedIn) {
                stringResource(R.string.bili_logged_in, account.username, account.mid, account.vip)
            } else {
                stringResource(R.string.bili_logged_out)
            },
            onClick = {
                viewModel.startQrLogin()
                isScanning = true
            },
        )
        ActionSettingRow(
            title = stringResource(R.string.bili_import_cookie),
            subtitle = stringResource(
                if (account.cookie.isEmpty()) R.string.bili_cookie_empty else R.string.bili_cookie_set
            ),
            onClick = { isEditingCookie = true },
        )
        if (account.isLoggedIn) {
            ActionSettingRow(
                title = stringResource(R.string.bili_logout),
                onClick = { viewModel.logout() },
            )
        }
    }

    if (isScanning) {
        ScanLoginDialog(
            viewModel = viewModel,
            onDismiss = {
                viewModel.cancelQrLogin()
                isScanning = false
            },
        )
    }

    if (isEditingCookie) {
        EditCookieDialog(
            initial = account.cookie,
            onDismiss = { isEditingCookie = false },
            onConfirm = {
                viewModel.setCookie(it)
                isEditingCookie = false
            },
        )
    }
}

@Composable
private fun ScanLoginDialog(viewModel: BilibiliAccountViewModel, onDismiss: () -> Unit) {
    val qr by viewModel.qr.collectAsStateWithLifecycle()
    val context = LocalContext.current

    LaunchedEffect(qr.status) {
        if (qr.status == "success") {
            delay(600)
            onDismiss()
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.bili_scan_login)) },
        text = {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Box(Modifier.size(220.dp), contentAlignment = Alignment.Center) {
                    val bitmap = rememberQrBitmap(qr.url)
                    if (bitmap == null) CircularProgressIndicator()
                    else Image(bitmap, contentDescription = null, modifier = Modifier.fillMaxWidth())
                }
                Text(
                    text = qrStatusText(qr),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.height(48.dp),
                )
                TextButton(onClick = viewModel::startQrLogin) {
                    Text(stringResource(R.string.bili_qr_refresh))
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(qr.url)))
                },
                enabled = qr.url.isNotEmpty(),
            ) { Text(stringResource(R.string.bili_qr_open)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) }
        },
    )
}

@Composable
private fun EditCookieDialog(
    initial: String,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit,
) {
    var text by remember { mutableStateOf(initial) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.bili_import_cookie)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = stringResource(R.string.bili_cookie_hint),
                    style = MaterialTheme.typography.bodySmall,
                )
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    minLines = 3,
                    maxLines = 6,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(text.trim()) }) {
                Text(stringResource(R.string.action_ok))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) }
        },
    )
}

@Composable
private fun qrStatusText(qr: BiliQr): String = when (qr.status) {
    "ready" -> stringResource(R.string.bili_qr_ready)
    "waiting" -> stringResource(R.string.bili_qr_unscanned)
    "scanned" -> stringResource(R.string.bili_qr_scanned)
    "expired" -> stringResource(R.string.bili_qr_expired)
    "success" -> stringResource(R.string.bili_qr_success)
    "failed" -> engineText(qr.message, emptyMap())
    else -> stringResource(R.string.bili_qr_loading)
}

@Composable
private fun rememberQrBitmap(url: String, size: Int = 512): ImageBitmap? {
    val bitmap by produceState<ImageBitmap?>(null, url, size) {
        value = if (url.isEmpty()) null
        else withContext(Dispatchers.Default) { toQrBitmap(url, size) }
    }
    return bitmap
}

private fun toQrBitmap(url: String, size: Int): ImageBitmap {
    val matrix = MultiFormatWriter().encode(
        url, BarcodeFormat.QR_CODE, size, size,
        mapOf(
            EncodeHintType.MARGIN to 2,
            EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M,
        ),
    )
    val pixels = IntArray(size * size)
    for (y in 0 until size) {
        for (x in 0 until size) {
            pixels[y * size + x] = if (matrix[x, y]) 0xFF000000.toInt() else 0xFFFFFFFF.toInt()
        }
    }
    return Bitmap.createBitmap(pixels, size, size, Bitmap.Config.ARGB_8888).asImageBitmap()
}
