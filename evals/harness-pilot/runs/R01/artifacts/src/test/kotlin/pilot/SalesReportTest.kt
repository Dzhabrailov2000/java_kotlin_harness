package pilot

import java.math.BigDecimal
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class SalesReportTest {
    private val report = SalesReport()

    @Test
    fun `groups and sorts unique sales without changing input`() {
        val sales = mutableListOf(
            Sale("b", "shared", "USD", BigDecimal("7")),
            Sale("a", "shared", "USD", BigDecimal("2.0")),
            Sale("a", "eur-order", "EUR", BigDecimal("3.25")),
            Sale("a", "second", "USD", BigDecimal("2.0")),
            Sale("a", "shared", "USD", BigDecimal("2.00")),
            Sale("b", "shared", "USD", BigDecimal("7")),
        )
        val original = sales.toList()

        val result = report.summarize(sales)

        assertEquals(
            listOf(
                SalesTotal("a", "EUR", 1, BigDecimal("3.25")),
                SalesTotal("a", "USD", 2, BigDecimal("4.0")),
                SalesTotal("b", "USD", 1, BigDecimal("7")),
            ),
            result,
        )
        assertEquals(original, sales)
    }

    @Test
    fun `rejects different amounts for the same sale`() {
        val sales = listOf(
            Sale("a", "order", "USD", BigDecimal("2.0")),
            Sale("a", "other", "USD", BigDecimal("5")),
            Sale("a", "order", "USD", BigDecimal("2.00000000000000000001")),
        )

        assertThrows(IllegalArgumentException::class.java) { report.summarize(sales) }
    }

    @Test
    fun `rejects different currencies for the same sale`() {
        val sales = listOf(
            Sale("a", "order", "USD", BigDecimal("2.0")),
            Sale("a", "order", "EUR", BigDecimal("2.00")),
        )

        assertThrows(IllegalArgumentException::class.java) { report.summarize(sales) }
    }

    @Test
    fun `adds amounts exactly without rounding`() {
        val sales = listOf(
            Sale("a", "first", "USD", BigDecimal("123456789012345678901234567890.12345678901234567890")),
            Sale("a", "second", "USD", BigDecimal("0.00000000000000000001")),
            Sale("a", "third", "USD", BigDecimal("-123456789012345678901234567890")),
        )

        assertEquals(
            listOf(SalesTotal("a", "USD", 3, BigDecimal("0.12345678901234567891"))),
            report.summarize(sales),
        )
    }

    @Test
    fun `returns an empty result for empty input`() {
        assertTrue(report.summarize(emptyList()).isEmpty())
    }
}
