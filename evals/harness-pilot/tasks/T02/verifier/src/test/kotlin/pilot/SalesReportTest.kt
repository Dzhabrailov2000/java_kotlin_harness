package pilot
import java.math.BigDecimal
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*
class SalesReportTest {
  private fun s(a:String,o:String,c:String,n:String)=Sale(a,o,c,BigDecimal(n))
  @Test fun `groups sorts retains accounts and removes only identical deliveries`() {
    val input=mutableListOf(s("b","1","RUB","1.10"),s("a","1","USD","2.0"),s("a","2","USD","3.125"),s("a","1","USD","2.00"),s("a","1b","EUR","4"))
    val before=input.toList();val r=SalesReport().summarize(input)
    assertEquals(listOf("a/EUR","a/USD","b/RUB"),r.map { "${it.accountId}/${it.currency}" })
    assertEquals(listOf(1,2,1),r.map { it.orders })
    assertEquals(0,r[1].amount.compareTo(BigDecimal("5.125")));assertEquals(before,input)
  }
  @Test fun `conflicting duplicates are not silently overwritten`() {
    for(other in listOf(s("a","1","USD","3"),s("a","1","EUR","2"))) {
      assertThrows(IllegalArgumentException::class.java) { SalesReport().summarize(listOf(s("a","1","USD","2"),other)) }
    }
  }
  @Test fun `empty and exact decimal sums`() {
    assertTrue(SalesReport().summarize(emptyList()).isEmpty())
    val r=SalesReport().summarize(listOf(s("a","1","USD","0.1"),s("a","2","USD","0.2")))
    assertEquals(0,r.single().amount.compareTo(BigDecimal("0.3")))
  }
}
