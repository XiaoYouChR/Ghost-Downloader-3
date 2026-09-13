package com.xychr.ghostdownloader.ui.settings

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class HeaderInputTest {
    @Test fun textRoundTripPreservesEmptyAndColonValues() {
        val entries = listOf(HeaderEntry("X-Empty", ""), HeaderEntry("Referer", "https://example.com:8080/a"))
        val result = parseHeaderText(toHeaderText(entries))
        assertTrue(result.isValid)
        assertEquals(entries, result.entries)
    }

    @Test fun textReportsEveryInvalidLineWithoutDiscardingIt() {
        val result = parseHeaderText("Accept: a\naccept: b\nmissing colon\nBad Name: c\n\nX-Ok: yes")
        assertEquals(listOf(2, 3, 4), result.invalidLines)
        assertEquals(5, result.entries.size)
    }

    @Test fun curlImportsSupportedFlagsWithoutImportingUrlOrBody() {
        val result = parseHeaderImport("curl 'https://example.com' -H 'Accept: */*' --header='X-Test: a:b' -b 'a=1' -A 'Agent 1' -e 'https://origin.test' --data-raw '-H body'")
        assertNull(result.error)
        assertEquals(listOf("Accept", "X-Test", "Cookie", "User-Agent", "Referer"), result.entries.map { it.name })
        assertEquals("a:b", result.entries[1].value)
    }

    @Test fun curlImportsJoinedFlagsAndContinuation() {
        val result = parseHeaderImport("curl https://example.com \\\n-H'Accept: */*' ^\n --header \"X-Test: a\\\"b\"")
        assertNull(result.error)
        assertEquals("a\"b", result.entries.last().value)
    }

    @Test fun curlRejectsMultipleRequestsAndFiles() {
        listOf("curl x -H 'A: b';curl y -H 'C: d'", "curl x -H 'A: b'\ncurl y -H 'C: d'").forEach {
            assertEquals(HeaderImportError.MULTIPLE_REQUESTS, parseHeaderImport(it).error)
        }
        listOf("curl x -H @headers.txt", "curl x -b cookies.txt", "curl x --config settings").forEach {
            assertEquals(HeaderImportError.FILE_INPUT, parseHeaderImport(it).error)
        }
    }

    @Test fun curlRejectsMalformedAndDuplicateHeaders() {
        assertEquals(HeaderImportError.QUOTES, parseHeaderImport("curl x -H 'A: b").error)
        assertEquals(HeaderImportError.INVALID_HEADERS, parseHeaderImport("curl x -H 'A: b' -H 'a: c'").error)
        assertEquals(HeaderImportError.EMPTY, parseHeaderImport("curl https://example.com").error)
    }

    @Test fun importReplacesOnlyMatchingNames() {
        val current = listOf(HeaderEntry("Accept", "old"), HeaderEntry("Cookie", "keep"))
        val incoming = listOf(HeaderEntry("accept", "new"), HeaderEntry("X-Test", "added"))
        assertEquals(listOf(current[1]) + incoming, buildMergedHeaders(current, incoming))
        assertEquals("old", current[0].value)
    }

    @Test fun controlCharactersAreNotValidValues() {
        assertFalse(matchHeaderValue("a\nb"))
        assertFalse(matchHeaderValue("a\u0000b"))
        assertTrue(matchHeaderValue("a\tb"))
    }
    @Test
    fun matchNames() {
        listOf("User-Agent", "Accept", "X-Custom", " Sec-CH-UA ").forEach {
            assertTrue(it, matchHeaderName(it))
        }
        listOf("", " ", "Bad Name", "Name: value", "请求头", "Bad\r\nName").forEach {
            assertFalse(it, matchHeaderName(it))
        }
    }
}
