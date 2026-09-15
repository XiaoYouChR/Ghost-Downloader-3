package com.xychr.ghostdownloader.model

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonClassDiscriminator

/**
 * 一次性的、需要告知用户的事件。做成 sealed 是为了穷尽性：两个出口都用 when 展开，
 * 将来加一种 Notice，编译器会同时在两处报错，而不是静默地什么都不做。
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
@JsonClassDiscriminator("kind")
sealed interface Notice {

    @Serializable
    @SerialName("taskCompleted")
    data class TaskCompleted(
        val taskId: String,
        val name: String,
        val path: String,
        val folder: String,
        /** Category 的图标名，由引擎按文件名匹配得出——分类知识留在引擎里，View 只做映射。 */
        val icon: String,
    ) : Notice

    @Serializable
    @SerialName("taskFailed")
    data class TaskFailed(
        val taskId: String,
        val name: String,
        val message: String,
        val params: Map<String, String> = emptyMap(),
    ) : Notice

    @Serializable
    @SerialName("diskSpace")
    data class DiskSpace(val free: Long, val needed: Long) : Notice

    @Serializable
    @SerialName("draftTaken")
    data class DraftTaken(val count: Int) : Notice

    @Serializable
    @SerialName("extensionUpdated")
    data class ExtensionUpdated(val version: String) : Notice
}
