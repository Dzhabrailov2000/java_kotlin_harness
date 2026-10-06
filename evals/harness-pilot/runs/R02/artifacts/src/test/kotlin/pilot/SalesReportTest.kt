package pilot

import java.math.BigDecimal
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test

class SalesReportTest {
    private val report = SalesReport()

    @Test
    fun `returns an empty result for empty input`() {
        assertEquals(emptyList<SalesTotal>(), report.summarize(emptyList()))
    }

    @Test
    fun `groups by account and currency and sorts without changing input`() {
        val sales = mutableListOf(
            Sale("b", "1", "USD", BigDecimal("7")),
            Sale("a", "2", "USD", BigDecimal("3")),
            Sale("b", "3", "EUR", BigDecimal("11")),
            Sale("a", "4", "EUR", BigDecimal("2")),
            Sale("a", "5", "USD", BigDecimal("5")),
        )
        val original = sales.toList()

        val totals = report.summarize(sales)

        assertEquals(
            listOf(
                SalesTotal("a", "EUR", 1, BigDecimal("2")),
                SalesTotal("a", "USD", 2, BigDecimal("8")),
                SalesTotal("b", "EUR", 1, BigDecimal("11")),
                SalesTotal("b", "USD", 1, BigDecimal("7")),
            ),
            totals,
        )
        assertEquals(original, sales)
    }

    @Test
    fun `counts identical deliveries and numerically equal amounts only once`() {
        val sale = Sale("a", "1", "USD", BigDecimal("2.0"))
        val sales = listOf(
            sale,
            Sale("a", "2", "USD", BigDecimal("3")),
            sale.copy(),
            sale.copy(amount = BigDecimal("2.00")),
        )

        for (input in listOf(sales, sales.reversed())) {
            val total = report.summarize(input).single()

            assertEquals("a", total.accountId)
            assertEquals("USD", total.currency)
            assertEquals(2, total.orders)
            assertEquals(0, BigDecimal("5").compareTo(total.amount))
        }
    }

    @Test
    fun `rejects conflicting amounts without changing input`() {
        val sale = Sale("a", "1", "USD", BigDecimal("2.0"))
        val sales = mutableListOf(sale, sale.copy(amount = BigDecimal("2.01")))
        val original = sales.toList()

        assertThrows(IllegalArgumentException::class.java) {
            report.summarize(sales)
        }

        assertEquals(original, sales)
    }

    @Test
    fun `rejects conflicting currencies even when amounts are numerically equal`() {
        val sale = Sale("a", "1", "USD", BigDecimal("2.0"))
        val sales = listOf(sale, sale.copy(currency = "EUR", amount = BigDecimal("2.00")))

        assertThrows(IllegalArgumentException::class.java) {
            report.summarize(sales)
        }
    }

    @Test
    fun `treats the same order identifier in different accounts as separate sales`() {
        val sales = listOf(
            Sale("b", "shared", "USD", BigDecimal("3")),
            Sale("a", "shared", "USD", BigDecimal("2")),
        )

        assertEquals(
            listOf(
                SalesTotal("a", "USD", 1, BigDecimal("2")),
                SalesTotal("b", "USD", 1, BigDecimal("3")),
            ),
            report.summarize(sales),
        )
    }

    @Test
    fun `adds amounts exactly without rounding`() {
        val sales = listOf(
            Sale("a", "1", "USD", BigDecimal("123456789012345678901234567890.123456789")),
            Sale("a", "2", "USD", BigDecimal("0.000000000123456789")),
            Sale("a", "3", "USD", BigDecimal("-0.1")),
        )

        val total = report.summarize(sales).single()

        assertEquals(3, total.orders)
        assertEquals(0, BigDecimal("123456789012345678901234567890.023456789123456789").compareTo(total.amount))
    }
}
