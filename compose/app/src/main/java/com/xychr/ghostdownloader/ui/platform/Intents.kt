package com.xychr.ghostdownloader.ui.platform

import android.content.Context
import android.content.Intent
import android.provider.Settings as SystemSettings
import androidx.core.net.toUri

// 部分设备上 Settings 页面不存在，官方文档要求调用方自行兜底
internal fun Context.start(intent: Intent): Boolean = runCatching {
    startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}.isSuccess

internal fun Context.appDetailsIntent(): Intent =
    Intent(SystemSettings.ACTION_APPLICATION_DETAILS_SETTINGS, "package:$packageName".toUri())
