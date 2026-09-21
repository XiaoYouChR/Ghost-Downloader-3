package com.xychr.ghostdownloader.ui.platform

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Environment
import android.os.PowerManager
import android.provider.Settings as SystemSettings
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.net.toUri

fun Context.hasStorageAccess(): Boolean =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        Environment.isExternalStorageManager()
    } else {
        ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE) ==
            PackageManager.PERMISSION_GRANTED
    }

fun Context.openStorageAccessSettings() {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        val perApp = Intent(
            SystemSettings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
            "package:$packageName".toUri(),
        )
        if (start(perApp)) return
        if (start(Intent(SystemSettings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))) return
    }
    start(appDetailsIntent())
}

fun Context.hasNotificationAccess(): Boolean =
    NotificationManagerCompat.from(this).areNotificationsEnabled()

/** 被永久拒绝后系统不再弹对话框，只能把用户送去设置页。 */
fun Context.canRequestNotifications(): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return false
    // LocalContext 拿到的是包了几层的 ContextWrapper，不是 Activity 本身
    var context: Context? = this
    while (context is ContextWrapper) {
        if (context is Activity) {
            return context.shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS)
        }
        context = context.baseContext
    }
    return false
}

fun Context.openNotificationSettings() {
    val intent = Intent(SystemSettings.ACTION_APP_NOTIFICATION_SETTINGS)
        .putExtra(SystemSettings.EXTRA_APP_PACKAGE, packageName)
    if (!start(intent)) start(appDetailsIntent())
}

fun Context.isBatteryUnrestricted(): Boolean =
    getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName)

fun Context.requestBatteryUnrestricted() {
    val request = Intent(
        SystemSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
        "package:$packageName".toUri(),
    )
    if (!start(request)) start(Intent(SystemSettings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
}

fun Context.canInstallPackages(): Boolean =
    packageManager.canRequestPackageInstalls()

fun Context.openInstallPackagesSettings() {
    val intent = Intent(
        SystemSettings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
        "package:$packageName".toUri(),
    )
    if (!start(intent)) start(appDetailsIntent())
}
