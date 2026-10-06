package pilot

import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController
import org.springframework.web.util.UriComponentsBuilder

@RestController
class ExportController(private val queue: ExportQueue) {
    @PostMapping("/exports")
    fun enqueueExport(@RequestBody request: Map<String, Any?>): ResponseEntity<ExportResponse> {
        val accountId = (request["accountId"] as? String)?.trim()
        val format = request["format"] as? String
        if (accountId.isNullOrEmpty() || (format != "csv" && format != "json")) {
            return ResponseEntity.badRequest().build()
        }

        val id = try {
            queue.enqueue(accountId, format)
        } catch (exception: QueueUnavailableException) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build()
        }

        val location = UriComponentsBuilder.fromPath("/exports").pathSegment(id).build().encode().toUri()
        return ResponseEntity.accepted().location(location).body(ExportResponse(id, "pending"))
    }
}

data class ExportResponse(val id: String, val state: String)
