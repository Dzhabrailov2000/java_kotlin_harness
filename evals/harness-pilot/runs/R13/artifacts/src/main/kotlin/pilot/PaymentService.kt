package pilot
import java.io.IOException
class PaymentService(private val gateway:PaymentGateway,private val newKey:()->String) {
  fun charge(request:Charge):Receipt {
    for(attempt in 1..3) {
      try { return gateway.charge(request,newKey()) }
      catch(e:IOException) { if(attempt==3)throw e }
    }
    error("unreachable")
  }
}
