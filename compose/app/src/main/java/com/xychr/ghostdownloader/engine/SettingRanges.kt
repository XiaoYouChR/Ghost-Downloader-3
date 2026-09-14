package com.xychr.ghostdownloader.engine

import com.xychr.ghostdownloader.model.SettingRange
import kotlinx.serialization.json.Json

object SettingRanges {

    private lateinit var ranges: Map<String, IntRange>

    fun load(json: String) {
        ranges = Json.decodeFromString<Map<String, SettingRange>>(json)
            .mapValues { (_, b) -> b.min..b.max }
    }

    operator fun get(name: String): IntRange = ranges.getValue(name)
}
