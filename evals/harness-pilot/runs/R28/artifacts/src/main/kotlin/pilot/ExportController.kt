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
    fun createExport(@RequestBody request: Map<String, Any?>): ResponseEntity<Map<String, String>> {
        val accountId = (request["accountId"] as? String)?.trim()
        val format = request["format"] as? String ?: return ResponseEntity.badRequest().build()
        if (accountId.isNullOrEmpty() || (format != "csv" && format != "json")) {
            return ResponseEntity.badRequest().build()
        }

        val id = try {
            queue.enqueue(accountId, format)
        } catch (_: QueueUnavailableException) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build()
        }

        val location = UriComponentsBuilder.fromPath("/exports/{id}")
            .encode()
            .buildAndExpand(id)
            .toUri()
        return ResponseEntity.accepted()
            .location(location)
            .body(mapOf("id" to id, "state" to "pending"))
    }
}
