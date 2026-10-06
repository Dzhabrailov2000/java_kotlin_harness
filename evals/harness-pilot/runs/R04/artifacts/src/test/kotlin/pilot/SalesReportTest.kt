package pilot

import java.math.BigDecimal
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test

class SalesReportTest {
    private val report = SalesReport()

    private fun sale(accountId: String, orderId: String, currency: String, amount: String) =
        Sale(accountId, orderId, currency, BigDecimal(amount))

    @Test
    fun `empty input gives empty result`() {
        assertEquals(emptyList<SalesTotal>(), report.summarize(emptyList()))
    }

    @Test
    fun `groups by account and currency sorted by account then currency`() {
        val result = report.summarize(
            listOf(
                sale("b", "1", "USD", "5.00"),
                sale("a", "2", "USD", "1.50"),
                sale("a", "1", "EUR", "3"),
                sale("a", "3", "USD", "2.25"),
                sale("b", "2", "EUR", "0.10"),
            )
        )

        assertEquals(
            listOf(
                SalesTotal("a", "EUR", 1, BigDecimal("3")),
                SalesTotal("a", "USD", 2, BigDecimal("3.75")),
                SalesTotal("b", "EUR", 1, BigDecimal("0.10")),
                SalesTotal("b", "USD", 1, BigDecimal("5.00")),
            ),
            result,
        )
    }

    @Test
    fun `identical redelivery is counted once`() {
        val result = report.summarize(
            listOf(
                sale("a", "1", "USD", "2.50"),
                sale("a", "2", "USD", "1.00"),
                sale("a", "1", "USD", "2.50"),
                sale("a", "1", "USD", "2.50"),
            )
        )

        assertEquals(listOf(SalesTotal("a", "USD", 2, BigDecimal("3.50"))), result)
    }

    @Test
    fun `redelivery with equivalent amount of another scale is counted once`() {
        val total = report.summarize(
            listOf(
                sale("a", "1", "USD", "2.0"),
                sale("a", "1", "USD", "2.00"),
            )
        ).single()

        assertEquals(1, total.orders)
        assertEquals(0, BigDecimal("2").compareTo(total.amount))
    }

    @Test
    fun `conflicting amount for the same order is rejected`() {
        assertThrows(IllegalArgumentException::class.java) {
            report.summarize(
                listOf(
                    sale("a", "1", "USD", "2.0"),
                    sale("a", "2", "USD", "1.00"),
                    sale("a", "1", "USD", "2.00"),
                    sale("a", "1", "USD", "2.01"),
                )
            )
        }
    }

    @Test
    fun `conflicting currency for the same order is rejected`() {
        assertThrows(IllegalArgumentException::class.java) {
            report.summarize(listOf(sale("a", "1", "USD", "2.00"), sale("a", "1", "EUR", "2.00")))
        }
    }

    @Test
    fun `same order id in different accounts are different sales`() {
        val result = report.summarize(
            listOf(
                sale("b", "1", "USD", "7.00"),
                sale("a", "1", "USD", "2.00"),
                sale("a", "2", "EUR", "4.00"),
                sale("b", "2", "EUR", "4.00"),
            )
        )

        assertEquals(
            listOf(
                SalesTotal("a", "EUR", 1, BigDecimal("4.00")),
                SalesTotal("a", "USD", 1, BigDecimal("2.00")),
                SalesTotal("b", "EUR", 1, BigDecimal("4.00")),
                SalesTotal("b", "USD", 1, BigDecimal("7.00")),
            ),
            result,
        )
    }

    @Test
    fun `amounts are summed exactly without rounding`() {
        val total = report.summarize(
            listOf(
                sale("a", "1", "USD", "12345678901234567890.123456789"),
                sale("a", "2", "USD", "0.000000001"),
                sale("a", "3", "USD", "0.1"),
            )
        ).single()

        assertEquals(BigDecimal("12345678901234567890.223456790"), total.amount)
    }

    @Test
    fun `input is not modified`() {
        val sales = arrayListOf(
            sale("b", "1", "USD", "1.0"),
            sale("a", "1", "USD", "2"),
            sale("b", "1", "USD", "1.00"),
        )
        val snapshot = sales.toList()

        report.summarize(sales)

        assertEquals(snapshot, sales)
    }
}
