package pilot

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test
import java.math.BigDecimal

class SalesReportTest {
    private val report = SalesReport()

    @Test
    fun `returns no totals for no sales`() {
        assertEquals(emptyList<SalesTotal>(), report.summarize(emptyList()))
    }

    @Test
    fun `sums sales exactly per account and currency sorted by account then currency`() {
        val sales = listOf(
            sale("b", "1", "USD", "1.10"),
            sale("a", "2", "USD", "0.1"),
            sale("b", "3", "EUR", "7"),
            sale("a", "4", "EUR", "5"),
            sale("a", "5", "USD", "0.2"),
            sale("a", "6", "USD", "3.005"),
        )

        assertTotals(
            listOf(
                SalesTotal("a", "EUR", 1, BigDecimal("5")),
                SalesTotal("a", "USD", 3, BigDecimal("3.305")),
                SalesTotal("b", "EUR", 1, BigDecimal("7")),
                SalesTotal("b", "USD", 1, BigDecimal("1.10")),
            ),
            report.summarize(sales),
        )
    }

    @Test
    fun `counts a repeated delivery once even when amount differs only in scale`() {
        val sales = listOf(
            sale("a", "1", "USD", "2.0"),
            sale("a", "2", "USD", "1"),
            sale("a", "1", "USD", "2.00"),
        )

        assertTotals(listOf(SalesTotal("a", "USD", 2, BigDecimal("3"))), report.summarize(sales))
    }

    @Test
    fun `rejects sales with the same account and order but different fields`() {
        val original = sale("a", "1", "USD", "2.00")

        assertThrows(IllegalArgumentException::class.java) {
            report.summarize(listOf(original, sale("a", "1", "USD", "2.01")))
        }
        assertThrows(IllegalArgumentException::class.java) {
            report.summarize(listOf(original, sale("a", "1", "EUR", "2.00")))
        }
    }

    @Test
    fun `treats the same order id in different accounts as different sales`() {
        val sales = listOf(
            sale("a", "1", "USD", "2"),
            sale("b", "1", "USD", "2"),
        )

        assertTotals(
            listOf(
                SalesTotal("a", "USD", 1, BigDecimal("2")),
                SalesTotal("b", "USD", 1, BigDecimal("2")),
            ),
            report.summarize(sales),
        )
    }

    @Test
    fun `leaves input unchanged`() {
        val sales = mutableListOf(
            sale("b", "1", "USD", "1"),
            sale("a", "2", "USD", "2.0"),
            sale("a", "2", "USD", "2.00"),
        )
        val snapshot = sales.toList()

        report.summarize(sales)

        assertEquals(snapshot, sales)
    }

    private fun sale(accountId: String, orderId: String, currency: String, amount: String) =
        Sale(accountId, orderId, currency, BigDecimal(amount))

    // Суммы сравниваются по значению: контракт не задает scale итога.
    private fun assertTotals(expected: List<SalesTotal>, actual: List<SalesTotal>) =
        assertEquals(expected.map { it.withNormalizedAmount() }, actual.map { it.withNormalizedAmount() })

    private fun SalesTotal.withNormalizedAmount() = copy(amount = amount.stripTrailingZeros())
}
