package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

typealias PackSettingsContent = @Composable (
    config: JsonObject,
    keys: PackKeys,
    set: (String, Any) -> Unit,
    send: suspend (String, List<Any?>) -> JsonElement,
) -> Unit

interface PackUi {
    val packId: String

    val settingsTitle: Int get() = 0

    val searchItems: List<Pair<Int, Int?>> get() = emptyList()

    val settingsContent: PackSettingsContent?
        get() = null

    val taskExtra: (@Composable (packFields: JsonObject) -> Unit)?
        get() = null

    val detailExtra: (@Composable (packFields: JsonObject) -> Unit)?
        get() = null

    val draftExtra: (@Composable (packFields: JsonObject, url: String, send: suspend (String, List<Any?>) -> Unit) -> Unit)?
        get() = null

    val editExtra: (@Composable (packFields: JsonObject) -> Unit)?
        get() = null
}
