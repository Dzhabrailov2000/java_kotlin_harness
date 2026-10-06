package pilot
import kotlinx.coroutines.*
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Timeout
import org.junit.jupiter.api.assertThrows
import java.io.FileNotFoundException
import java.io.IOException
import java.util.concurrent.atomic.AtomicInteger
import kotlin.coroutines.CoroutineContext
import kotlin.coroutines.EmptyCoroutineContext

@Timeout(10)
class BatchLoaderTest {
  private class ProgramError(message:String):Error(message)
  private fun found(id:String) = ItemResult.Found(id,"v-$id")

  @Test fun `keeps order and duplicates when calls finish out of order`() = runBlocking<Unit> {
    val delays = mapOf("a" to 30L,"b" to 5L,"c" to 15L)
    val calls = AtomicInteger()
    val loader = BatchLoader { id -> calls.incrementAndGet(); delay(delays.getValue(id)); "v-$id" }
    val ids = listOf("a","b","a","c","b")
    assertEquals(ids.map(::found),loader.load(ids,5))
    assertEquals(ids.size,calls.get())
  }

  @Test fun `runs up to parallelism calls at once and never more`() {
    for (context in listOf(EmptyCoroutineContext,Dispatchers.Default)) {
      assertPeakConcurrency(context,size = 10,parallelism = 3,expected = 3)
      assertPeakConcurrency(context,size = 3,parallelism = 10,expected = 3)
      assertPeakConcurrency(context,size = 4,parallelism = 1,expected = 1)
    }
  }

  private fun assertPeakConcurrency(context:CoroutineContext,size:Int,parallelism:Int,expected:Int) = runBlocking(context) {
    val inFlight = AtomicInteger()
    val peak = AtomicInteger()
    val saturated = CompletableDeferred<Unit>()
    val loader = BatchLoader { id ->
      val now = inFlight.incrementAndGet()
      try {
        peak.accumulateAndGet(now) { a,b -> maxOf(a,b) }
        if (now == expected) saturated.complete(Unit)
        // Hangs into @Timeout unless `expected` calls really run at the same time.
        saturated.await()
        yield()
        "v-$id"
      } finally { inFlight.decrementAndGet() }
    }
    val ids = List(size) { "id$it" }
    assertEquals(ids.map(::found),loader.load(ids,parallelism))
    assertEquals(expected,peak.get(),"peak for size=$size parallelism=$parallelism in $context")
  }

  @Test fun `IOException fails only its own element`() = runBlocking<Unit> {
    val loader = BatchLoader { id -> if (id.startsWith("bad")) throw FileNotFoundException(id) else "v-$id" }
    val ids = listOf("a","bad1","b","bad1","bad2")
    val expected = listOf(found("a"),ItemResult.Failed("bad1"),found("b"),ItemResult.Failed("bad1"),ItemResult.Failed("bad2"))
    assertEquals(expected,loader.load(ids,2))
  }

  @Test fun `IOException on one occurrence does not fail its duplicate`() = runBlocking<Unit> {
    val attempts = AtomicInteger()
    val loader = BatchLoader { id -> if (attempts.incrementAndGet() == 1) throw IOException("flaky") else "v-$id" }
    assertEquals(listOf(ItemResult.Failed("x"),found("x")),loader.load(listOf("x","x"),1))
  }

  @Test fun `program errors propagate and cancel the rest of the batch`() {
    for (error in listOf(IllegalStateException("boom"),ProgramError("boom"))) {
      val started = AtomicInteger()
      val cancelled = AtomicInteger()
      val loader = BatchLoader { id ->
        started.incrementAndGet()
        if (id == "boom") { yield(); throw error }
        try { awaitCancellation() } catch (e:CancellationException) { cancelled.incrementAndGet(); throw e }
      }
      val thrown = assertThrows<Throwable> { runBlocking { loader.load(listOf("a","boom","b","c"),3) } }
      assertEquals(error::class,thrown::class)
      assertEquals("boom",thrown.message)
      // "c" waits for a permit and must never reach the client.
      assertEquals(3,started.get())
      assertEquals(2,cancelled.get())
    }
  }

  @Test fun `cancellation thrown by the client propagates instead of becoming Failed`() {
    val loader = BatchLoader { id -> if (id == "b") throw CancellationException("stop") else "v-$id" }
    val thrown = assertThrows<CancellationException> { runBlocking { loader.load(listOf("a","b","c"),2) } }
    assertEquals("stop",thrown.message)
  }

  @Test fun `caller cancellation stops the batch without results`() = runBlocking<Unit> {
    val started = AtomicInteger()
    val cancelled = AtomicInteger()
    val loader = BatchLoader { _ ->
      started.incrementAndGet()
      try { awaitCancellation() } catch (e:CancellationException) { cancelled.incrementAndGet(); throw e }
    }
    val result = CompletableDeferred<List<ItemResult>>()
    val job = launch { result.complete(loader.load(List(5) { "id$it" },2)) }
    while (started.get() < 2) yield()
    job.cancelAndJoin()
    assertTrue(job.isCancelled)
    assertFalse(result.isCompleted)
    assertEquals(2,started.get())
    assertEquals(2,cancelled.get())
  }

  @Test fun `non-positive parallelism is rejected before any client call`() {
    val calls = AtomicInteger()
    val loader = BatchLoader { id -> calls.incrementAndGet(); "v-$id" }
    for (parallelism in listOf(0,-1,Int.MIN_VALUE)) {
      assertThrows<IllegalArgumentException> { runBlocking { loader.load(listOf("a","b"),parallelism) } }
      assertThrows<IllegalArgumentException> { runBlocking { loader.load(emptyList(),parallelism) } }
    }
    assertEquals(0,calls.get())
  }

  @Test fun `empty batch returns empty list`() = runBlocking<Unit> {
    val loader = BatchLoader { error("client must not be called") }
    assertEquals(emptyList<ItemResult>(),loader.load(emptyList(),3))
  }
}
