package com.xychr.ghostdownloader.engine

import com.xychr.ghostdownloader.model.SettingRange
import kotlinx.serialization.json.Json

// 合法范围由引擎的 RangeValidator 定义，启动时装一次——它不随运行时变化。
object SettingRanges {

    private val ranges = mutableMapOf<String, IntRange>()

    fun load(json: String) {
        ranges.clear()
        Json.decodeFromString<Map<String, SettingRange>>(json)
            .forEach { (name, bound) -> ranges[name] = bound.min..bound.max }
    }

    operator fun get(name: String): IntRange = ranges.getValue(name)
}
