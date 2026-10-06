package pilot

import java.math.BigDecimal

data class Sale(val accountId: String, val orderId: String, val currency: String, val amount: BigDecimal)
data class SalesTotal(val accountId: String, val currency: String, val orders: Int, val amount: BigDecimal)

class SalesReport {
    private data class SaleKey(val accountId: String, val orderId: String)
    private data class TotalKey(val accountId: String, val currency: String)

    fun summarize(sales: List<Sale>): List<SalesTotal> {
        val uniqueSales = mutableMapOf<SaleKey, Sale>()
        val totals = mutableMapOf<TotalKey, SalesTotal>()

        for (sale in sales) {
            val saleKey = SaleKey(sale.accountId, sale.orderId)
            val existingSale = uniqueSales.putIfAbsent(saleKey, sale)
            if (existingSale != null) {
                require(existingSale.currency == sale.currency && existingSale.amount.compareTo(sale.amount) == 0) {
                    "Conflicting sale for accountId=${sale.accountId}, orderId=${sale.orderId}"
                }
                continue
            }

            val totalKey = TotalKey(sale.accountId, sale.currency)
            val total = totals[totalKey]
            totals[totalKey] = if (total == null) {
                SalesTotal(sale.accountId, sale.currency, 1, sale.amount)
            } else {
                total.copy(orders = total.orders + 1, amount = total.amount.add(sale.amount))
            }
        }

        return totals.values.sortedWith(compareBy<SalesTotal> { it.accountId }.thenBy { it.currency })
    }
}
