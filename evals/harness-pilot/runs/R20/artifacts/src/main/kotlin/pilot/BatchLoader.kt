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
  suspend fun load(ids:List<String>,parallelism:Int):List<ItemResult> = coroutineScope {
    require(parallelism > 0) { "parallelism must be positive" }
    val semaphore = Semaphore(parallelism)
    ids.map { id ->
      async {
        semaphore.withPermit {
          try {
            ItemResult.Found(id, client.fetch(id))
          } catch (e: IOException) {
            ItemResult.Failed(id)
          }
        }
      }
    }.awaitAll()
  }
}
