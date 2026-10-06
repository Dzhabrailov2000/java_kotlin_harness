package pilot
import java.math.BigDecimal
data class Sale(val accountId:String,val orderId:String,val currency:String,val amount:BigDecimal)
data class SalesTotal(val accountId:String,val currency:String,val orders:Int,val amount:BigDecimal)
class SalesReport {
    fun summarize(sales: List<Sale>): List<SalesTotal> =
        uniqueOrders(sales)
            .groupBy { TotalKey(it.accountId, it.currency) }
            .map { (key, orders) ->
                val amount = orders.map(Sale::amount).reduce(BigDecimal::add)
                SalesTotal(key.accountId, key.currency, orders.size, amount)
            }
            .sortedWith(compareBy(SalesTotal::accountId, SalesTotal::currency))

    private fun uniqueOrders(sales: List<Sale>): Collection<Sale> {
        val firstDeliveries = mutableMapOf<OrderKey, Sale>()
        for (sale in sales) {
            val first = firstDeliveries.getOrPut(OrderKey(sale.accountId, sale.orderId)) { sale }
            require(sale.isRedeliveryOf(first)) {
                "Conflicting sales for account '${sale.accountId}', order '${sale.orderId}': $first vs $sale"
            }
        }
        return firstDeliveries.values
    }

    // Key fields already match; amounts are compared by value, so 2.0 and 2.00 are the same.
    private fun Sale.isRedeliveryOf(first: Sale) =
        currency == first.currency && amount.compareTo(first.amount) == 0

    private data class OrderKey(val accountId: String, val orderId: String)

    private data class TotalKey(val accountId: String, val currency: String)
}
