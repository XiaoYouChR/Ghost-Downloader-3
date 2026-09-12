package com.xychr.ghostdownloader.model

import kotlinx.serialization.Serializable

@Serializable
data class DraftFile(
    val index: Int = 0,
    val path: String = "",
    val size: Long = 0,
    val isSelected: Boolean = true,
)

@Serializable
data class DraftOption(val key: String = "", val label: String = "")

/**
 * 字段是引擎 `draft()` 的并集：基础字段人人有，其余由 pack 的 `draftFields` 按需补。
 * 缺字段就用默认值兜底，所以这里不认 pack——有 videoTiers 才画画质，duration 大于 0 才画裁剪。
 */
@Serializable
data class DraftItem(
    val url: String = "",
    val isParsing: Boolean = true,
    val name: String = "",
    val categoryChoice: String? = null,
    val categoryId: String = "",
    val outputFolder: String = "",
    val targetFolder: String = "",
    val fileSize: Long = 0,
    val files: List<DraftFile> = emptyList(),
    val error: TaskError? = null,
    val videoTiers: List<DraftOption> = emptyList(),
    val audioTiers: List<DraftOption> = emptyList(),
    val subtitles: List<DraftOption> = emptyList(),
    val videoTier: String = "",
    val audioTier: String = "",
    val subtitleLanguages: List<String> = emptyList(),
    val isVideoEnabled: Boolean = false,
    val isAudioEnabled: Boolean = false,
    val isCoverEnabled: Boolean = false,
    val hasCover: Boolean = false,
    val canRenameFiles: Boolean = false,
    val duration: Int = 0,
    val startTime: Int = 0,
    val endTime: Int = 0,
    val canProbeMedia: Boolean = false,
    val hasMediaInfo: Boolean = false,
    val canProbePlaylist: Boolean = false,
    val hasPreview: Boolean = false,
    val audioLanguages: List<DraftOption> = emptyList(),
    val selectedAudioLanguages: List<String> = emptyList(),
)

@Serializable
data class PreviewSheet(
    val url: String,
    val columns: Int,
    val rows: Int,
    val times: List<Double>,
)

@Serializable
data class DraftPreview(
    val sheets: List<PreviewSheet> = emptyList(),
    val headers: Map<String, String> = emptyMap(),
)
