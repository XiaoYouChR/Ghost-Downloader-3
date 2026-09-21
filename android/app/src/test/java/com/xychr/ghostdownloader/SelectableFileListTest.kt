package com.xychr.ghostdownloader

import com.xychr.ghostdownloader.ui.components.FileRow
import com.xychr.ghostdownloader.ui.components.FolderRow
import com.xychr.ghostdownloader.ui.components.SelectableFile
import com.xychr.ghostdownloader.ui.components.TreeRow
import com.xychr.ghostdownloader.ui.components.buildCollapsed
import com.xychr.ghostdownloader.ui.components.buildRows
import org.junit.Assert.assertEquals
import org.junit.Test

class SelectableFileListTest {

    private fun file(index: Int, name: String, vararg groups: String): SelectableFile {
        val path = (groups.toList() + name).joinToString("/")
        return SelectableFile(index, path, groups.toList(), 0)
    }

    private fun part(index: Int, episode: String, name: String) =
        SelectableFile(index, "$episode - $name", listOf(episode), 0)

    private fun labels(tree: List<TreeRow>) = tree.map { row ->
        val indent = "  ".repeat(row.depth)
        when (row) {
            is FolderRow -> "$indent${row.key.last()}/"
            is FileRow -> "$indent${row.file.index}"
        }
    }

    private fun folder(files: List<SelectableFile>, key: List<String>) =
        buildRows(files, emptySet()).filterIsInstance<FolderRow>().first { it.key == key }

    private val mixed = listOf(file(0, "a.txt", "甲"), file(1, "b.txt", "甲"), file(2, "c.txt", "乙"))

    @Test
    fun filesNestUnderTheirFolders() {
        val tree = buildRows(
            listOf(file(0, "01.mp4", "第01话"), file(1, "02.mp4", "第01话"), file(2, "01.mp4", "第02话")),
            emptySet(),
        )
        assertEquals(listOf("第01话/", "  0", "  1", "第02话/", "  2"), labels(tree))
    }

    @Test
    fun collapseHidesDescendantsButKeepsTheFolderItself() {
        val files = listOf(file(0, "01.mp4", "第01话"), file(1, "01.mp4", "第02话"))
        assertEquals(
            listOf("第01话/", "第02话/", "  1"),
            labels(buildRows(files, collapsed = setOf(listOf("第01话")))),
        )
    }

    @Test
    fun collapsingANestedFolderKeepsItsAncestors() {
        val files = listOf(file(0, "c.txt", "a", "b"), file(1, "d.txt", "a", "b"), file(2, "e.txt", "a"))
        assertEquals(
            listOf("a/", "  b/", "  2"),
            labels(buildRows(files, collapsed = setOf(listOf("a", "b")))),
        )
    }

    @Test
    fun aFileNamedLikeItsFolderDoesNotMergeWithIt() {
        val tree = buildRows(listOf(file(0, "b.txt", "a"), file(1, "c.txt", "a", "b")), emptySet())
        assertEquals(listOf("a/", "  0", "  b/", "    1"), labels(tree))
    }

    @Test
    fun siblingFoldersKeepSeparateBranches() {
        val tree = buildRows(
            listOf(file(0, "b.txt", "a"), file(1, "c.txt", "a"), file(2, "e.txt", "d")),
            emptySet(),
        )
        assertEquals(listOf("a/", "  0", "  1", "d/", "  2"), labels(tree))
    }

    @Test
    fun filesWithoutFoldersSitAtTheRoot() {
        assertEquals(listOf("0"), labels(buildRows(listOf(file(0, "readme.txt")), emptySet())))
    }

    @Test
    fun folderDescendantsCoverEveryNestedFile() {
        val files = listOf(file(0, "c.txt", "a", "b"), file(1, "d.txt", "a"))
        assertEquals(listOf(0, 1), folder(files, listOf("a")).descendants)
    }

    @Test
    fun collapsingATopFolderAlsoHidesItsNestedFolders() {
        val files = listOf(
            file(0, "c.txt", "a", "b"), file(1, "d.txt", "a", "b"), file(2, "e.txt", "a"), file(3, "f.txt"),
        )
        assertEquals(listOf("a/", "3"), labels(buildRows(files, setOf(listOf("a")))))
    }

    @Test
    fun aSlashInAGroupLabelDoesNotSplitTheGroup() {
        val tree = buildRows(
            listOf(part(0, "向北/北国恋曲", "P1"), part(1, "向北/北国恋曲", "P2")),
            emptySet(),
        )
        assertEquals(listOf("向北/北国恋曲/", "  0", "  1"), labels(tree))
    }

    @Test
    fun aGroupNamedLikeTwoNestedGroupsKeepsItsOwnDescendants() {
        val files = listOf(file(0, "x.txt", "a/b"), file(1, "y.txt", "a", "b"))
        assertEquals(listOf(0), folder(files, listOf("a/b")).descendants)
    }

    @Test
    fun nothingSelectedStartsExpanded() {
        assertEquals(emptySet<List<String>>(), buildCollapsed(mixed, emptySet()))
    }

    @Test
    fun aGroupWithoutSelectionStartsCollapsed() {
        assertEquals(setOf(listOf("乙")), buildCollapsed(mixed, setOf(1)))
    }

    @Test
    fun aFullySelectedListStartsExpanded() {
        assertEquals(emptySet<List<String>>(), buildCollapsed(mixed, setOf(0, 1, 2)))
    }
}
