package pilot
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Test
import org.springframework.http.MediaType
import org.springframework.mock.web.MockHttpServletResponse
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.test.web.servlet.setup.MockMvcBuilders
import tools.jackson.module.kotlin.jacksonObjectMapper
import tools.jackson.module.kotlin.readValue

class ExportControllerTest {
    private val queue = RecordingExportQueue()
    private val mockMvc = MockMvcBuilders.standaloneSetup(ExportController(queue)).build()

    @Test
    fun `accepts csv export and enqueues trimmed account id once`() {
        val response = postExport("""{"accountId":"  acc-1 ","format":"csv"}""")

        assertEquals(202, response.status)
        assertEquals("/exports/exp-1", response.getHeader("Location"))
        assertEquals(
            mapOf("id" to "exp-1", "state" to "pending"),
            jacksonObjectMapper().readValue<Map<String, Any?>>(response.contentAsString),
        )
        assertEquals(listOf("acc-1" to "csv"), queue.calls)
    }

    @Test
    fun `accepts json export`() {
        val response = postExport("""{"accountId":"acc-1","format":"json"}""")

        assertEquals(202, response.status)
        assertEquals(listOf("acc-1" to "json"), queue.calls)
    }

    @Test
    fun `rejects invalid input without enqueueing`() {
        val invalidBodies = listOf(
            """{"accountId":"   ","format":"csv"}""",
            """{"accountId":null,"format":"csv"}""",
            """{"format":"csv"}""",
            """{"accountId":"acc-1","format":"xml"}""",
            """{"accountId":"acc-1","format":"CSV"}""",
            """{"accountId":"acc-1"}""",
            """{"accountId":"acc-1","format":""",
        )

        invalidBodies.forEach { body -> assertEquals(400, postExport(body).status, body) }
        assertEquals(emptyList<Pair<String, String>>(), queue.calls)
    }

    @Test
    fun `returns 503 without exception message when queue is unavailable`() {
        val message = "broker 10.0.0.5:5672 refused connection"
        queue.failure = QueueUnavailableException(message)

        val response = postExport("""{"accountId":"acc-1","format":"csv"}""")

        assertEquals(503, response.status)
        assertFalse(response.contentAsString.contains(message))
        assertEquals(listOf("acc-1" to "csv"), queue.calls)
    }

    @Test
    fun `does not enqueue when client does not accept json`() {
        val response = mockMvc.perform(
            post("/exports")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_PLAIN)
                .content("""{"accountId":"acc-1","format":"csv"}"""),
        ).andReturn().response

        assertEquals(406, response.status)
        assertEquals(emptyList<Pair<String, String>>(), queue.calls)
    }

    private fun postExport(body: String): MockHttpServletResponse =
        mockMvc.perform(post("/exports").contentType(MediaType.APPLICATION_JSON).content(body)).andReturn().response
}

private class RecordingExportQueue : ExportQueue {
    val calls = mutableListOf<Pair<String, String>>()
    var failure: RuntimeException? = null

    override fun enqueue(accountId: String, format: String): String {
        calls += accountId to format
        failure?.let { throw it }
        return "exp-1"
    }
}
