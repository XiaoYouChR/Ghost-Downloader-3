package com.xychr.ghostdownloader.draft

import com.xychr.ghostdownloader.packs.controlList
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DraftControlTest {

    private fun fields(json: String) = Json.parseToJsonElement(json).jsonObject

    @Test fun decodesSingleSelectControl() {
        val controls = fields(
            """{"controls":[{"id":"video","title":"视频","value":"80-7","isOptional":true,
                "options":[{"key":"80-7","label":"1080P"},{"key":"64-7","label":"720P"}]}]}"""
        ).controlList()

        val video = controls.single()
        assertEquals("video", video.id)
        assertEquals("视频", video.title)
        assertEquals("80-7", video.value)
        assertTrue(video.isOptional)
        assertFalse(video.isMultiple)
        assertEquals(listOf("80-7", "64-7"), video.options.map { it.key })
    }

    @Test fun decodesMultipleSelectControl() {
        val controls = fields(
            """{"controls":[{"id":"language","value":"ja,en","isMultiple":true,
                "options":[{"key":"ja","label":"日本語"},{"key":"en","label":"English"}]}]}"""
        ).controlList()

        assertTrue(controls.single().isMultiple)
    }

    @Test fun defaultsAreOff() {
        val controls = fields(
            """{"controls":[{"id":"audio","options":[{"key":"0","label":"最佳音质"}]}]}"""
        ).controlList()

        val audio = controls.single()
        assertEquals("", audio.value)
        assertFalse(audio.isOptional)
        assertFalse(audio.isMultiple)
    }

    @Test fun dropsControlWithoutOptions() {
        val controls = fields(
            """{"controls":[{"id":"empty","title":"空","options":[]},
                {"id":"kept","options":[{"key":"0","label":"有一个"}]}]}"""
        ).controlList()

        assertEquals(listOf("kept"), controls.map { it.id })
    }

    @Test fun missingControlsKeyYieldsNothing() {
        assertTrue(fields("""{"subtitles":[]}""").controlList().isEmpty())
    }
}
