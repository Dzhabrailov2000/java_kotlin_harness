package pilot
import kotlinx.coroutines.*
import java.io.IOException
fun interface ItemClient { suspend fun fetch(id:String):String }
sealed interface ItemResult {
  data class Found(val id:String,val value:String):ItemResult
  data class Failed(val id:String):ItemResult
}
class BatchLoader(private val client:ItemClient) {
  suspend fun load(ids:List<String>,parallelism:Int):List<ItemResult> = coroutineScope {
    ids.map { id -> async { runCatching { ItemResult.Found(id,client.fetch(id)) }.getOrElse { ItemResult.Failed(id) } } }.awaitAll()
  }
}
