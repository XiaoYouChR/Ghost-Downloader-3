package com.xychr.ghostdownloader

import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.components.draft.*
import org.junit.Assert.*
import org.junit.Test

class DraftStateTest {
    @Test fun parsingCanBeConfirmed() {
        assertTrue(DraftState(items = listOf(DraftItem(url = "one"))).canConfirm)
        assertFalse(DraftState().canConfirm)
        assertFalse(DraftState(urls = "one", isWorking = true).canConfirm)
    }

    @Test fun unparsedInputCanBeConfirmedBeforeDebounce() {
        assertTrue(DraftState(urls = "one").canConfirm)
    }

    @Test fun invalidFolderBlocksConfirm() {
        assertFalse(DraftState(urls = "one", globalFolder = "relative/path").canConfirm)
        assertTrue(DraftState(urls = "one", globalFolder = "/absolute/path").canConfirm)
        assertTrue(DraftState(urls = "one", globalFolder = "").canConfirm)
    }


    @Test fun previewUsesActualTimestampsAndClampsToLastFrame() {
        val preview = DraftPreview(listOf(
            PreviewSheet("one", 2, 2, listOf(0.0, 2.0, 4.0, 6.0)),
            PreviewSheet("two", 2, 2, listOf(8.0, 10.0))))
        assertEquals(PreviewFrame(0, 3), preview.frameAt(7))
        assertEquals(PreviewFrame(1, 0), preview.frameAt(8))
        assertEquals(PreviewFrame(1, 1), preview.frameAt(100))
        assertNull(DraftPreview().frameAt(0))
    }
}
