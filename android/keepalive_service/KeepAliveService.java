package org.ghostdownloader;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

/**
 * 同进程前台服务：把宿主进程钉在前台优先级, 下载/浏览器服务切后台不被回收。
 * 不声明 android:process(与 Activity 同进程); 文案经 Intent extra "text" 传入; 起停由 Python 侧控制(见 android_keepalive.py)。
 */
public class KeepAliveService extends Service {
    private static final String CHANNEL_ID = "gd3_keepalive";
    private static final int NOTIFICATION_ID = 0x47443301;

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String text = (intent != null) ? intent.getStringExtra("text") : null;
        if (text == null) {
            text = "正在后台运行";
        }
        Notification notification = buildNotification(text);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
        // 进程若被杀，无 Python 引擎单独重启服务无意义，故不黏；起停全由 app 主动控制。
        return START_NOT_STICKY;
    }

    private Notification buildNotification(String text) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, "后台任务", NotificationManager.IMPORTANCE_LOW);
            manager.createNotificationChannel(channel);
        }

        Notification.Builder builder = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);

        Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (launch != null) {
            int pendingFlags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                pendingFlags |= PendingIntent.FLAG_IMMUTABLE;
            }
            builder.setContentIntent(PendingIntent.getActivity(this, 0, launch, pendingFlags));
        }

        return builder
                .setSmallIcon(getApplicationInfo().icon)
                .setContentTitle("Ghost Downloader")
                .setContentText(text)
                .setOngoing(true)
                .build();
    }
}
