package pilot
import java.io.IOException
data class Charge(val accountId:String,val cents:Long)
data class Receipt(val id:String)
class RejectedCharge:RuntimeException()
fun interface PaymentGateway { fun charge(request:Charge,idempotencyKey:String):Receipt }
