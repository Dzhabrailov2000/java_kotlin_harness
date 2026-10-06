package pilot
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.net.URI
@RestController
class ExportController(private val queue: ExportQueue) {
  @PostMapping("/exports")
  fun submitExport(@RequestBody request: Map<String, String?>): ResponseEntity<*> {
    val account=request["accountId"]?.trim()
    val format=request["format"]
    if(account.isNullOrEmpty() || format !in setOf("csv","json")) return ResponseEntity.badRequest().build<Void>()
    val id=try { queue.enqueue(account, requireNotNull(format)) } catch(e:QueueUnavailableException) { return ResponseEntity.status(503).build<Void>() }
    return ResponseEntity.accepted().location(URI.create("/exports/$id")).body(mapOf("id" to id,"state" to "pending"))
  }
}
