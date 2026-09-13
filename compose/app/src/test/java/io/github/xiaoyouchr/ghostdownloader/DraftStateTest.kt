package com.xychr.ghostdownloader

import com.xychr.ghostdownloader.ui.draft.*
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

    @Test fun unchangedEditorDoesNotWriteEngine() {
        val edit = buildEdits(DraftItem(name = "one", isParsing = false))
        DraftPart.entries.forEach { assertTrue(buildChanges(edit, edit, it).isEmpty()) }
    }

    @Test fun fileSelectionKeepsEngineIndexes() {
        val initial = buildEdits(DraftItem(files = listOf(
            DraftFile(index = 3, path = "a"), DraftFile(index = 17, path = "b"))))
        val changed = initial.copy(files = initial.files.map { it.copy(isSelected = it.index == 17) })
        assertEquals(listOf(DraftChange("setSelection", listOf("17"))), buildChanges(initial, changed, DraftPart.Files))
        assertTrue(initial.files.all { it.isSelected })
    }

    @Test fun mediaEditorDoesNotOverwriteNameOrOtherEditors() {
        val initial = buildEdits(DraftItem(name = "one", isVideoEnabled = true))
        val edited = initial.copy(name = "two", isVideoEnabled = false, subtitles = listOf("en"))
        assertEquals(listOf(DraftChange("setTrack", listOf("video", false))), buildChanges(initial, edited, DraftPart.Media))
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
