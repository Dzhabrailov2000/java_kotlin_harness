package pilot

import java.io.IOException
import java.io.UncheckedIOException
import java.util.concurrent.atomic.AtomicInteger
import java.util.function.Supplier
import java.util.stream.Stream
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertSame
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows

class CatalogReaderTest {
    private val reader = CatalogReader()

    @Test
    fun `returns trimmed non-empty lines in source order keeping duplicates`() {
        val result = reader.read({ Stream.of("  b ", "", "a", "   ", "\tb\t", "a") }, 10)

        assertEquals(listOf("b", "a", "b", "a"), result)
    }

    @Test
    fun `limit counts only non-empty lines`() {
        val result = reader.read({ Stream.of("", " x ", "  ", "y", "z") }, 2)

        assertEquals(listOf("x", "y"), result)
    }

    @Test
    fun `emptiness is decided after trim`() {
        // trim strips control characters but keeps unicode spaces such as EM SPACE
        val result = reader.read({ Stream.of("\u0000", " \u0001 ", " ", " ok ") }, 10)

        assertEquals(listOf(" ", "ok"), result)
    }

    @Test
    fun `negative limit is rejected before the source is opened`() {
        val opened = AtomicInteger()

        assertThrows<IllegalArgumentException> {
            reader.read({ opened.incrementAndGet(); Stream.of("a") }, -1)
        }
        assertEquals(0, opened.get())
    }

    @Test
    fun `zero limit returns empty list without opening the source`() {
        val opened = AtomicInteger()

        val result = reader.read({ opened.incrementAndGet(); Stream.of("a") }, 0)

        assertEquals(emptyList<String>(), result)
        assertEquals(0, opened.get())
    }

    @Test
    fun `infinite source is read only up to the limit and closed`() {
        val pulled = AtomicInteger()
        val closed = AtomicInteger()
        val source = Supplier {
            Stream.iterate(0) { it + 1 }
                .peek { pulled.incrementAndGet() }
                .map { if (it % 2 == 0) " line$it " else " " }
                .onClose { closed.incrementAndGet() }
        }

        assertEquals(listOf("line0", "line2", "line4"), reader.read(source, 3))
        assertEquals(5, pulled.get())
        assertEquals(1, closed.get())
    }

    @Test
    fun `parallel source is read lazily in encounter order`() {
        val pulled = AtomicInteger()
        val source = Supplier {
            Stream.iterate(0) { it + 1 }.parallel().peek { pulled.incrementAndGet() }.map { "line$it" }
        }

        assertEquals(listOf("line0", "line1", "line2"), reader.read(source, 3))
        assertEquals(3, pulled.get())
    }

    @Test
    fun `source is closed after full traversal`() {
        val closed = AtomicInteger()

        reader.read({ Stream.of("a", " ").onClose { closed.incrementAndGet() } }, 10)

        assertEquals(1, closed.get())
    }

    @Test
    fun `traversal failure propagates and the source is closed`() {
        val failure = IllegalStateException("broken line")
        val closed = AtomicInteger()
        val source = Supplier {
            Stream.of("a", "b", "c")
                .map { if (it == "b") throw failure else it }
                .onClose { closed.incrementAndGet() }
        }

        val thrown = assertThrows<IllegalStateException> { reader.read(source, 5) }

        assertSame(failure, thrown)
        assertEquals(1, closed.get())
    }

    @Test
    fun `close failure is suppressed by the traversal failure`() {
        val failure = IllegalStateException("broken line")
        val closeFailure = UncheckedIOException(IOException("close failed"))
        val source = Supplier { Stream.generate<String> { throw failure }.onClose { throw closeFailure } }

        val thrown = assertThrows<IllegalStateException> { reader.read(source, 5) }

        assertSame(failure, thrown)
        assertEquals(listOf(closeFailure), thrown.suppressed.toList())
    }

    @Test
    fun `close failure after successful traversal is propagated`() {
        val closeFailure = UncheckedIOException(IOException("close failed"))

        val thrown = assertThrows<UncheckedIOException> {
            reader.read({ Stream.of("a").onClose { throw closeFailure } }, 5)
        }

        assertSame(closeFailure, thrown)
    }

    @Test
    fun `open failure propagates`() {
        val failure = UncheckedIOException(IOException("cannot open"))

        val thrown = assertThrows<UncheckedIOException> { reader.read({ throw failure }, 5) }

        assertSame(failure, thrown)
    }
}
