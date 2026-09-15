package com.xychr.ghostdownloader.features.bili_pack

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.annotation.StringRes
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.TaskError
import com.xychr.ghostdownloader.ui.components.ChoiceField
import com.xychr.ghostdownloader.ui.components.ErrorText
import kotlinx.coroutines.delay

private enum class LoginMode(@StringRes val label: Int) {
    Qr(R.string.bili_mode_qr),
    Sms(R.string.bili_mode_sms),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LoginSheet(viewModel: BilibiliAccountViewModel, onDismiss: () -> Unit) {
    val account by viewModel.account.collectAsStateWithLifecycle()
    var mode by rememberSaveable { mutableStateOf(LoginMode.Qr) }
    val wasLoggedIn = remember { account.isLoggedIn }

    LaunchedEffect(account.isLoggedIn) {
        if (!wasLoggedIn && account.isLoggedIn) {
            delay(600)
            onDismiss()
        }
    }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(bottom = 24.dp).imePadding(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                LoginMode.entries.forEachIndexed { index, entry ->
                    SegmentedButton(
                        selected = mode == entry,
                        onClick = { mode = entry },
                        shape = SegmentedButtonDefaults.itemShape(index, LoginMode.entries.size),
                    ) { Text(stringResource(entry.label)) }
                }
            }
            when (mode) {
                LoginMode.Qr -> QrSection(viewModel)
                LoginMode.Sms -> SmsSection(viewModel)
            }
        }
    }
}

@Composable
private fun QrSection(viewModel: BilibiliAccountViewModel) {
    val qr by viewModel.qr.collectAsStateWithLifecycle()
    val context = LocalContext.current

    Column(
        Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        LaunchedEffect(Unit) { viewModel.startQrLogin() }
        DisposableEffect(Unit) { onDispose { viewModel.cancelQrLogin() } }

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
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(onClick = viewModel::startQrLogin) {
                Text(stringResource(R.string.bili_qr_refresh))
            }
            TextButton(
                onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(qr.url))) },
                enabled = qr.url.isNotEmpty(),
            ) { Text(stringResource(R.string.bili_qr_open)) }
        }
    }
}

@Composable
private fun SmsSection(viewModel: BilibiliAccountViewModel) {
    val sms by viewModel.sms.collectAsStateWithLifecycle()

    LaunchedEffect(Unit) { if (sms.countries.isEmpty()) viewModel.refreshCountries() }

    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(stringResource(R.string.bili_sms_hint), style = MaterialTheme.typography.bodySmall)

        val countryOptions = remember(sms.countries) { sms.countries.map { it.cid.toString() to it.label } }
        ChoiceField(
            label = stringResource(R.string.bili_sms_country),
            value = sms.cid.toString(),
            options = countryOptions,
            onSelect = { viewModel.setCountry(it.toInt()) },
            modifier = Modifier.fillMaxWidth(),
        )

        OutlinedTextField(
            value = sms.tel,
            onValueChange = viewModel::setTel,
            label = { Text(stringResource(R.string.bili_sms_phone)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Button(
            onClick = viewModel::requestSmsCode,
            enabled = !sms.isSending && sms.isTelValid,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(if (sms.isSent) R.string.bili_sms_sent else R.string.bili_sms_send))
        }

        OutlinedTextField(
            value = sms.code,
            onValueChange = viewModel::setCode,
            label = { Text(stringResource(R.string.bili_sms_code)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Button(
            onClick = viewModel::loginSms,
            enabled = !sms.isSending && sms.isSent && sms.code.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) { Text(stringResource(R.string.bili_sms_submit)) }

        if (sms.isSending) CircularProgressIndicator()

        val captchaFailure = sms.captchaFailure
        ErrorText(captchaFailure?.let { TaskError(stringResource(it.message)) } ?: sms.error)
    }

    sms.captcha?.let { params ->
        Dialog(
            onDismissRequest = viewModel::cancelCaptcha,
            properties = DialogProperties(usePlatformDefaultWidth = false),
        ) {
            GeetestCaptcha(
                params = params,
                onResult = viewModel::onCaptchaResult,
                onCancel = viewModel::cancelCaptcha,
                onFailure = viewModel::onCaptchaFailed,
            )
        }
    }
}
