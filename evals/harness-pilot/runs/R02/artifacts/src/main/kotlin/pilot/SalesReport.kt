package pilot

import java.math.BigDecimal

data class Sale(val accountId:String,val orderId:String,val currency:String,val amount:BigDecimal)
data class SalesTotal(val accountId:String,val currency:String,val orders:Int,val amount:BigDecimal)

class SalesReport {
    fun summarize(sales: List<Sale>): List<SalesTotal> {
        val uniqueSales = mutableMapOf<SaleKey, Sale>()
        for (sale in sales) {
            val key = SaleKey(sale.accountId, sale.orderId)
            val previous = uniqueSales[key]
            if (previous == null) {
                uniqueSales[key] = sale
            } else {
                require(previous.currency == sale.currency && previous.amount.compareTo(sale.amount) == 0) {
                    "Conflicting sales for accountId=${sale.accountId}, orderId=${sale.orderId}"
                }
            }
        }

        return uniqueSales.values
            .groupBy { AccountCurrency(it.accountId, it.currency) }
            .map { (key, orders) ->
                SalesTotal(
                    accountId = key.accountId,
                    currency = key.currency,
                    orders = orders.size,
                    amount = orders.sumOf { it.amount },
                )
            }
            .sortedWith(compareBy<SalesTotal> { it.accountId }.thenBy { it.currency })
    }

    private data class SaleKey(val accountId: String, val orderId: String)

    private data class AccountCurrency(val accountId: String, val currency: String)
}
