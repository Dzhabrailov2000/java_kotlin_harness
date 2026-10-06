package pilot
import kotlinx.coroutines.*
import java.io.IOException
import java.util.concurrent.atomic.AtomicInteger
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*
class BatchLoaderTest {
  @Test fun `limits active requests preserves duplicate inputs and order`() = runBlocking {
    val active=AtomicInteger();val peak=AtomicInteger()
    val client=ItemClient { id -> val n=active.incrementAndGet();peak.accumulateAndGet(n,::maxOf);try { delay(20);id.uppercase() } finally { active.decrementAndGet() } }
    val ids=listOf("b","a","b","c","d","e")
    val result=BatchLoader(client).load(ids,2)
    assertEquals(ids.map { ItemResult.Found(it,it.uppercase()) },result);assertTrue(peak.get()<=2);assertTrue(peak.get()>1)
  }
  @Test fun `io failure is per item and programmer errors propagate`(): Unit = runBlocking {
    val q=BatchLoader(ItemClient { if(it=="bad")throw IOException("down") else it })
    assertEquals(listOf(ItemResult.Failed("bad"),ItemResult.Found("ok","ok")),q.load(listOf("bad","ok"),2))
    assertThrows(IllegalStateException::class.java) { runBlocking { BatchLoader(ItemClient { error("bug") }).load(listOf("x"),1) } }
  }
  @Test fun `client cancellation is never successful data`() {
    assertThrows(CancellationException::class.java) { runBlocking { BatchLoader(ItemClient { throw CancellationException("cancel") }).load(listOf("x"),1) } }
  }
  @Test fun `invalid limit fails before client calls`() {
    var calls=0;val q=BatchLoader(ItemClient { calls++;it })
    for(n in listOf(0,-1))assertThrows(IllegalArgumentException::class.java) { runBlocking { q.load(listOf("x"),n) } }
    assertEquals(0,calls)
  }
}
