package pilot
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController
import org.springframework.web.util.UriComponentsBuilder

private val SUPPORTED_FORMATS = setOf("csv", "json")

@RestController
class ExportController(private val queue: ExportQueue) {
    private val log = LoggerFactory.getLogger(javaClass)

    // produces проверяет Accept до вызова метода: иначе экспорт встал бы в очередь, а клиент получил бы 406.
    @PostMapping("/exports", produces = [MediaType.APPLICATION_JSON_VALUE])
    fun enqueue(@RequestBody request: ExportRequest): ResponseEntity<ExportResponse> {
        val accountId = request.accountId?.trim()
        val format = request.format?.takeIf { it in SUPPORTED_FORMATS }
        if (accountId.isNullOrEmpty() || format == null) {
            return ResponseEntity.badRequest().build()
        }
        val id = try {
            queue.enqueue(accountId, format)
        } catch (e: QueueUnavailableException) {
            log.warn("Export queue is unavailable", e)
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build()
        }
        val location = UriComponentsBuilder.fromPath("/exports/{id}").build(id)
        return ResponseEntity.accepted().location(location).body(ExportResponse(id, "pending"))
    }
}

data class ExportRequest(val accountId: String?, val format: String?)

data class ExportResponse(val id: String, val state: String)
