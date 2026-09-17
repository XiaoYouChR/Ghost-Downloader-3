package com.xychr.ghostdownloader.packs

import com.xychr.ghostdownloader.model.DraftOption
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject

data class DraftControl(
    val id: String,
    val options: List<DraftOption>,
    val title: String = "",
    val value: String = "",
    val isMultiple: Boolean = false,
    val isOptional: Boolean = false,
)

fun JsonObject.controlList(): List<DraftControl> =
    (this["controls"] as? JsonArray).orEmpty().mapNotNull { element ->
        val control = element.jsonObject
        val options = control.optionList("options")
        if (options.isEmpty()) return@mapNotNull null
        DraftControl(
            id = control.str("id"),
            options = options,
            title = control.str("title"),
            value = control.str("value"),
            isMultiple = control.bool("isMultiple"),
            isOptional = control.bool("isOptional"),
        )
    }
