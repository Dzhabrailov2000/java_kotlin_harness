package pilot

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.springframework.http.MediaType
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.test.web.servlet.setup.MockMvcBuilders
import tools.jackson.databind.json.JsonMapper

class ExportControllerTest {
    private val mapper = JsonMapper.builder().build()

    @Test
    fun `accepted exports are pending and enqueue the normalized account once`() {
        for (format in listOf("csv", "json")) {
            val queue = RecordingQueue()
            val response = mvc(queue).perform(
                post("/exports")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""{"accountId":" \taccount-123\n ","format":"$format"}""")
            ).andReturn().response

            assertEquals(202, response.status)
            assertEquals("/exports/export-123", response.getHeader("Location"))
            assertTrue(response.contentType?.startsWith(MediaType.APPLICATION_JSON_VALUE) == true)
            assertEquals(
                mapper.readTree("""{"id":"export-123","state":"pending"}"""),
                mapper.readTree(response.contentAsString)
            )
            assertEquals(listOf("account-123" to format), queue.calls)
        }
    }

    @Test
    fun `invalid requests do not call the queue`() {
        val queue = RecordingQueue()
        val mvc = mvc(queue)
        val invalidBodies = listOf(
            "",
            "{",
            "null",
            "[]",
            "42",
            "\"account-123\"",
            "{}",
            """{"format":"csv"}""",
            """{"accountId":null,"format":"csv"}""",
            """{"accountId":"","format":"csv"}""",
            """{"accountId":" \t\n ","format":"csv"}""",
            """{"accountId":123,"format":"csv"}""",
            """{"accountId":true,"format":"csv"}""",
            """{"accountId":[],"format":"csv"}""",
            """{"accountId":{},"format":"csv"}""",
            """{"accountId":"account-123"}""",
            """{"accountId":"account-123","format":null}""",
            """{"accountId":"account-123","format":""}""",
            """{"accountId":"account-123","format":"xml"}""",
            """{"accountId":"account-123","format":"CSV"}""",
            """{"accountId":"account-123","format":" csv "}""",
            """{"accountId":"account-123","format":123}""",
            """{"accountId":"account-123","format":true}""",
            """{"accountId":"account-123","format":[]}""",
            """{"accountId":"account-123","format":{}}"""
        )

        for (body in invalidBodies) {
            val response = mvc.perform(
                post("/exports").contentType(MediaType.APPLICATION_JSON).content(body)
            ).andReturn().response

            assertEquals(400, response.status, "Request body: $body")
            assertTrue(queue.calls.isEmpty(), "Queue called for request body: $body")
        }
    }

    @Test
    fun `unavailable queue returns 503 without exposing the exception message`() {
        val queue = RecordingQueue(unavailable = true)
        val response = mvc(queue).perform(
            post("/exports")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""{"accountId":" account-123 ","format":"csv"}""")
        ).andReturn().response

        assertEquals(503, response.status)
        assertEquals("", response.contentAsString)
        assertEquals(null, response.getHeader("Location"))
        assertEquals(listOf("account-123" to "csv"), queue.calls)
    }

    private fun mvc(queue: ExportQueue): MockMvc =
        MockMvcBuilders.standaloneSetup(ExportController(queue)).build()

    private class RecordingQueue(private val unavailable: Boolean = false) : ExportQueue {
        val calls = mutableListOf<Pair<String, String>>()

        override fun enqueue(accountId: String, format: String): String {
            calls.add(accountId to format)
            if (unavailable) {
                throw QueueUnavailableException("Sensitive queue connection details")
            }
            return "export-123"
        }
    }
}
