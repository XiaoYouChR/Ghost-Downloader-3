package com.xychr.ghostdownloader.model

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonClassDiscriminator

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
