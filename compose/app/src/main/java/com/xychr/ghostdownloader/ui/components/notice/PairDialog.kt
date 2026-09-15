package com.xychr.ghostdownloader.ui.components.notice

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.PairRequest

/**
 * 配对是把控制权交给外部客户端的安全决策，必须打断用户——所以是 Dialog 而不是 Snackbar。
 * 来源地址和那句"仅在你刚刚点过自动配对时允许"是防钓鱼的核心，别精简掉。
 */
@Composable
fun PairDialog(
    pair: PairRequest,
    onApprove: () -> Unit,
    onReject: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onReject,
        title = { Text(stringResource(R.string.pair_title)) },
        text = {
            Text(
                stringResource(
                    R.string.pair_detail,
                    pair.peerAddress,
                    pair.clientKind.ifEmpty { stringResource(R.string.pair_unknown_client) },
                    pair.extensionVersion,
                ),
                style = MaterialTheme.typography.bodyMedium,
            )
        },
        confirmButton = { TextButton(onApprove) { Text(stringResource(R.string.pair_approve)) } },
        dismissButton = { TextButton(onReject) { Text(stringResource(R.string.pair_reject)) } },
    )
}
