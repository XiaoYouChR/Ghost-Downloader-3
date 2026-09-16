package com.xychr.ghostdownloader.ui.components.notice

import android.content.Context
import com.xychr.ghostdownloader.ui.navigation.DESTINATION_DRAFT
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.model.Notice
import com.xychr.ghostdownloader.ui.navigation.toDestination
import com.xychr.ghostdownloader.ui.util.formatSize

/** destination 非空时才给 action——按钮没有去处就不该出现。 */
data class NoticeMessage(val text: String, val action: String?, val destination: String?)

fun Context.noticeMessage(notice: Notice): NoticeMessage = when (notice) {
    is Notice.TaskCompleted -> NoticeMessage(
        getString(R.string.notice_completed_inline, notice.name), null, null,
    )

    is Notice.TaskFailed -> NoticeMessage(
        getString(R.string.notice_failed, notice.name) + "：" + engineText(notice.message, notice.params),
        getString(R.string.notice_view),
        toDestination(notice.taskId),
    )

    is Notice.DiskSpace -> NoticeMessage(
        getString(R.string.notice_disk_space_desc, formatSize(notice.free), formatSize(notice.needed)),
        null, null,
    )

    is Notice.DraftTaken -> NoticeMessage(
        resources.getQuantityString(R.plurals.notice_draft_taken_desc, notice.count, notice.count),
        getString(R.string.notice_view),
        DESTINATION_DRAFT,
    )

    is Notice.ExtensionUpdated -> NoticeMessage(
        getString(R.string.notice_extension_updated, notice.version), null, null,
    )
}
