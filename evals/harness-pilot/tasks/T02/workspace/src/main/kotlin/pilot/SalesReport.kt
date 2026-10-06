package pilot
import java.math.BigDecimal
data class Sale(val accountId:String,val orderId:String,val currency:String,val amount:BigDecimal)
data class SalesTotal(val accountId:String,val currency:String,val orders:Int,val amount:BigDecimal)
class SalesReport { fun summarize(sales:List<Sale>):List<SalesTotal> = TODO("implement") }
