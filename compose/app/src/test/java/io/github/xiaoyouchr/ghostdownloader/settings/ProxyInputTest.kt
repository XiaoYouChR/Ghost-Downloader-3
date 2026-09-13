package com.xychr.ghostdownloader.ui.settings

import org.junit.Assert.*
import org.junit.Test

class ProxyInputTest {
    @Test fun roundTrip() {
        listOf("Off", "Auto", "http://127.0.0.1:7890", "socks5://alice:secret@proxy.example.com:1080").forEach {
            assertEquals(it, buildProxy(parseProxy(it)))
            assertTrue(matchProxy(parseProxy(it)))
        }
    }
    @Test fun changingModeRetainsCustomDraftButDoesNotSubmitIt() {
        val custom = parseProxy("http://127.0.0.1:7890")
        val off = custom.copy(mode = ProxyMode.OFF)
        assertEquals("Off", buildProxy(off))
        assertEquals(custom, off.copy(mode = ProxyMode.CUSTOM))
    }
    @Test fun invalidInputDoesNotSilentlyBecomeAuto() {
        listOf("http://999.0.0.1:7890", "http://127.0.0.1:0", "http://127.0.0.1:65536",
            "http://bad host:80", "http://alice:@proxy.example.com:80", "ftp://proxy.example.com:80").forEach {
            assertFalse(it, matchProxy(parseProxy(it)))
        }
    }
    @Test fun hostRejectsPathsAndUnsupportedAddresses() {
        listOf("https://example.com", "example.com/path", "::1", "-bad.example.com", "").forEach {
            assertFalse(it, matchProxyHost(it))
        }
    }
}
