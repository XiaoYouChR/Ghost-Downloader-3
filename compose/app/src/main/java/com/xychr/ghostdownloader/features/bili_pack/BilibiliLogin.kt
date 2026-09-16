package com.xychr.ghostdownloader.features.bili_pack

import android.graphics.Bitmap
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
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
import com.xychr.ghostdownloader.i18n.toTaskError
import com.xychr.ghostdownloader.model.TaskError
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
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
data class CaptchaParams(
    val gt: String = "",
    val challenge: String = "",
)

@Serializable
data class CaptchaResult(
    val challenge: String,
    val validate: String,
    val seccode: String,
)

@Serializable
data class Country(
    val cid: Int = 0,
    val label: String = "",
)

@Serializable
data class CountryChoices(
    val defaultCid: Int = 86,
    val countries: List<Country> = emptyList(),
)

@Serializable
data class BiliQr(
    val status: String = "loading",
    val url: String = "",
    val message: String = "",
)

enum class SmsAction { Countries, Send, Login }

data class SmsFailure(val action: SmsAction, val error: TaskError)

data class SmsState(
    val cid: Int = 86,
    val tel: String = "",
    val code: String = "",
    val countries: List<Country> = emptyList(),
    val captcha: CaptchaParams? = null,
    val captchaFailure: CaptchaFailure? = null,
    val pending: SmsAction? = null,
    val isSent: Boolean = false,
    val failure: SmsFailure? = null,
) {
    val isTelValid: Boolean get() = tel.matches(Regex("\\d{6,20}"))
    val isSending: Boolean get() = pending != null
}

class BilibiliAccountViewModel(
    private val send: suspend (String, List<Any>) -> Unit,
    private val fetchCaptcha: suspend () -> CaptchaParams,
    private val fetchCountries: suspend () -> CountryChoices,
    private val submitSmsCode: suspend (Int, String, CaptchaResult) -> Unit,
    accountFlow: Flow<BiliAccount>,
    qrFlow: Flow<BiliQr>,
) : ViewModel() {

    val account: StateFlow<BiliAccount> =
        accountFlow.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), BiliAccount())

    val qr: StateFlow<BiliQr> =
        qrFlow.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), BiliQr())

    private val mutableSms = MutableStateFlow(SmsState())
    val sms: StateFlow<SmsState> = mutableSms.asStateFlow()

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

    private fun smsAction(action: SmsAction, block: suspend () -> Unit) {
        mutableSms.value = mutableSms.value.copy(pending = action, failure = null, captchaFailure = null)
        viewModelScope.launch {
            try {
                block()
                mutableSms.value = mutableSms.value.copy(pending = null)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                mutableSms.value = mutableSms.value.copy(
                    pending = null,
                    failure = SmsFailure(action, error.toTaskError()),
                )
            }
        }
    }

    fun refreshCountries() = smsAction(SmsAction.Countries) {
        val choices = fetchCountries()
        mutableSms.value = mutableSms.value.copy(countries = choices.countries, cid = choices.defaultCid)
    }

    fun setCountry(cid: Int) { mutableSms.value = mutableSms.value.copy(cid = cid) }
    fun setTel(tel: String) { mutableSms.value = mutableSms.value.copy(tel = tel) }
    fun setCode(code: String) { mutableSms.value = mutableSms.value.copy(code = code) }

    fun requestSmsCode() = smsAction(SmsAction.Send) {
        mutableSms.value = mutableSms.value.copy(captcha = fetchCaptcha())
    }

    fun cancelCaptcha() { mutableSms.value = mutableSms.value.copy(captcha = null) }

    fun onCaptchaFailed(failure: CaptchaFailure) {
        mutableSms.value = mutableSms.value.copy(captcha = null, pending = null, captchaFailure = failure)
    }

    fun onCaptchaResult(result: CaptchaResult) {
        val current = mutableSms.value
        mutableSms.value = current.copy(captcha = null)
        smsAction(SmsAction.Send) {
            submitSmsCode(current.cid, current.tel, result)
            mutableSms.value = mutableSms.value.copy(isSent = true)
        }
    }

    fun loginSms() {
        val current = mutableSms.value
        smsAction(SmsAction.Login) { send("loginSms", listOf(current.cid, current.tel, current.code)) }
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
            fetchCaptcha = { EngineRepository.query("requestPack", packId, "fetchCaptcha") },
            fetchCountries = { EngineRepository.query("requestPack", packId, "fetchCountries") },
            submitSmsCode = { cid, tel, captcha ->
                EngineRepository.invoke(
                    "requestPack", packId, "sendSmsCode", cid, tel, EngineRepository.encode(captcha),
                )
            },
            accountFlow = EngineRepository.observe("pack:$packId:accountState"),
            qrFlow = EngineRepository.observe("pack:$packId:qrState"),
        )
    },
) {
    val account by viewModel.account.collectAsStateWithLifecycle()
    var isLoggingIn by remember { mutableStateOf(false) }
    var isEditingCookie by remember { mutableStateOf(false) }

    SettingSection {
        ActionSettingRow(
            title = stringResource(R.string.bili_login),
            subtitle = if (account.isLoggedIn) {
                stringResource(R.string.bili_logged_in, account.username, account.mid, account.vip)
            } else {
                stringResource(R.string.bili_logged_out)
            },
            onClick = { isLoggingIn = true },
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

    if (isLoggingIn) {
        LoginSheet(viewModel) { viewModel.cancelQrLogin(); isLoggingIn = false }
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
fun qrStatusText(qr: BiliQr): String = when (qr.status) {
    "ready" -> stringResource(R.string.bili_qr_ready)
    "waiting" -> stringResource(R.string.bili_qr_unscanned)
    "scanned" -> stringResource(R.string.bili_qr_scanned)
    "expired" -> stringResource(R.string.bili_qr_expired)
    "success" -> stringResource(R.string.bili_qr_success)
    "failed" -> engineText(qr.message)
    else -> stringResource(R.string.bili_qr_loading)
}

@Composable
fun rememberQrBitmap(url: String, size: Int = 512): ImageBitmap? {
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
