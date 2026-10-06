package pilot
import java.math.BigDecimal
data class Sale(val accountId:String,val orderId:String,val currency:String,val amount:BigDecimal)
data class SalesTotal(val accountId:String,val currency:String,val orders:Int,val amount:BigDecimal)
class SalesReport {
  private data class OrderKey(val accountId:String,val orderId:String)
  private data class TotalKey(val accountId:String,val currency:String)
  fun summarize(sales:List<Sale>):List<SalesTotal> {
    val unique=linkedMapOf<OrderKey,Sale>()
    for(sale in sales) {
      val old=unique.putIfAbsent(OrderKey(sale.accountId,sale.orderId),sale)
      require(old==null || old.currency==sale.currency && old.amount.compareTo(sale.amount)==0)
    }
    return unique.values.groupBy { TotalKey(it.accountId,it.currency) }.map { (key,orders) ->
      SalesTotal(key.accountId,key.currency,orders.size,orders.fold(BigDecimal.ZERO) { n,s -> n+s.amount })
    }.sortedWith(compareBy(SalesTotal::accountId,SalesTotal::currency))
  }
}
