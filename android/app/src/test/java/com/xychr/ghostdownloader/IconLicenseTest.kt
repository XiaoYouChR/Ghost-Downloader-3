package com.xychr.ghostdownloader

import org.junit.Assert.*
import org.junit.Test
import java.io.File

class IconLicenseTest {
    @Test fun everyMaterialSymbolsDrawableIsListedAndEveryLedgerEntryExists() {
        val ledger = File("src/main/assets/licenses/material-symbols.txt")
        val listed = Regex("""^(ic_[a-z_]+\.xml) ->""", RegexOption.MULTILINE)
            .findAll(ledger.readText()).map { it.groupValues[1] }.toSet()
        val drawables = File("src/main/res/drawable").listFiles().orEmpty()
            .map { it.name }.filter { it.startsWith("ic_") }.toSet()

        assertEquals("台账登记了但文件不存在", emptySet<String>(), listed - drawables)
        assertEquals("未登记进台账", emptySet<String>(), (drawables - notFromMaterialSymbols) - listed)
    }

    private companion object {
        val notFromMaterialSymbols = setOf("ic_notification_download.xml")
    }
}
