package pilot
import java.math.BigDecimal
data class Sale(val accountId:String,val orderId:String,val currency:String,val amount:BigDecimal)
data class SalesTotal(val accountId:String,val currency:String,val orders:Int,val amount:BigDecimal)

class SalesReport {
    fun summarize(sales: List<Sale>): List<SalesTotal> =
        deduplicate(sales)
            .groupBy { TotalKey(it.accountId, it.currency) }
            .map { (key, group) ->
                SalesTotal(
                    accountId = key.accountId,
                    currency = key.currency,
                    orders = group.size,
                    amount = group.sumOf { it.amount },
                )
            }
            .sortedWith(compareBy({ it.accountId }, { it.currency }))

    private fun deduplicate(sales: List<Sale>): List<Sale> =
        sales
            .groupBy { SaleKey(it.accountId, it.orderId) }
            .map { (key, deliveries) ->
                val original = deliveries.first()
                require(deliveries.all { it.hasSameFieldsAs(original) }) { "Conflicting sales for $key" }
                original
            }
}

private data class SaleKey(val accountId: String, val orderId: String)

private data class TotalKey(val accountId: String, val currency: String)

// compareTo вместо equals: equals различает 2.0 и 2.00 по scale, а это одна сумма.
private fun Sale.hasSameFieldsAs(other: Sale): Boolean =
    accountId == other.accountId &&
        orderId == other.orderId &&
        currency == other.currency &&
        amount.compareTo(other.amount) == 0
