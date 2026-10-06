package pilot
import java.io.IOException
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*
class PaymentContractTest {
  @Test fun `lost response does not repeat charge and key belongs to one logical call`() {
    val paid=mutableMapOf<String,Receipt>();var seq=0;var requests=0
    val gateway=PaymentGateway { _,key -> requests++;val previous=paid[key];if(previous!=null)previous else { paid[key]=Receipt("paid-${paid.size}");throw IOException("response lost after commit") } }
    val service=PaymentService(gateway) { "key-${seq++}" }
    val receipt=service.charge(Charge("a",100));assertEquals("paid-0",receipt.id);assertEquals(1,paid.size);assertEquals(2,requests)
    service.charge(Charge("a",100));assertEquals(2,paid.size)
  }
  @Test fun `rejection is not retried and exhausted io keeps exception`() {
    var calls=0;val rejected=RejectedCharge()
    assertSame(rejected,assertThrows(RejectedCharge::class.java) { PaymentService(PaymentGateway { _,_->calls++;throw rejected }) { "k" }.charge(Charge("a",1)) });assertEquals(1,calls)
    calls=0;val io=IOException("network")
    assertSame(io,assertThrows(IOException::class.java) { PaymentService(PaymentGateway { _,_->calls++;throw io }) { "k" }.charge(Charge("a",1)) });assertEquals(3,calls)
  }
}
