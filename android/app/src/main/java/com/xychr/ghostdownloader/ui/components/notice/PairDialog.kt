package com.xychr.ghostdownloader.ui.components.notice

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.PairRequest

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
