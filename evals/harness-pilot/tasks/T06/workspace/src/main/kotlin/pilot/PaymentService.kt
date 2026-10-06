package pilot
import java.io.IOException
class PaymentService(private val gateway:PaymentGateway,private val newKey:()->String) {
  fun charge(request:Charge):Receipt {
    val key=newKey()
    for(attempt in 1..3) {
      try { return gateway.charge(request,key) }
      catch(e:IOException) { if(attempt==3)throw e }
    }
    error("unreachable")
  }
}
