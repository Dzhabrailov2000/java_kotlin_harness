package pilot
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import java.io.IOException
fun interface ItemClient { suspend fun fetch(id:String):String }
sealed interface ItemResult {
  data class Found(val id:String,val value:String):ItemResult
  data class Failed(val id:String):ItemResult
}
class BatchLoader(private val client:ItemClient) {
  suspend fun load(ids:List<String>,parallelism:Int):List<ItemResult> {
    require(parallelism > 0) { "parallelism must be > 0, was $parallelism" }
    val permits = Semaphore(parallelism)
    return coroutineScope {
      ids.map { id -> async { permits.withPermit { fetch(id) } } }.awaitAll()
    }
  }
  // Only IOException is a per-item failure; cancellation and other throwables reach the caller.
  private suspend fun fetch(id:String):ItemResult =
    try { ItemResult.Found(id,client.fetch(id)) } catch (e:IOException) { ItemResult.Failed(id) }
}
