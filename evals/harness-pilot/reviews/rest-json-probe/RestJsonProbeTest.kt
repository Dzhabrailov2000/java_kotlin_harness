package pilot

import org.junit.jupiter.api.Test
import org.springframework.http.MediaType
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.test.web.servlet.setup.MockMvcBuilders
import tools.jackson.databind.json.JsonMapper

@org.springframework.context.annotation.Configuration(proxyBeanMethods = false)
@org.springframework.web.servlet.config.annotation.EnableWebMvc
@org.springframework.context.annotation.ComponentScan(basePackages = ["pilot"])
class PosthocWebConfig

class RestJsonProbeTest {
    @Test
    fun `records scalar coercion without assigning a benchmark score`() {
        val mapper = JsonMapper.builder().build()
        for (body in listOf(
            """{"accountId":"123","format":"csv"}""",
            """{"accountId":123,"format":"csv"}""",
            """{"accountId":true,"format":"csv"}""",
        )) {
            val calls = mutableListOf<String>()
            val queue = object : ExportQueue {
                override fun enqueue(accountId: String, format: String): String {
                    calls.add("$accountId/$format")
                    return "job-17"
                }
            }
            val context = org.springframework.web.context.support.AnnotationConfigWebApplicationContext()
            context.servletContext = org.springframework.mock.web.MockServletContext()
            context.register(PosthocWebConfig::class.java)
            context.addBeanFactoryPostProcessor { it.registerSingleton("fixtureExportQueue", queue) }
            context.refresh()
            try {
                val response = MockMvcBuilders.webAppContextSetup(context).build()
                    .perform(post("/exports").contentType(MediaType.APPLICATION_JSON).content(body))
                    .andReturn().response
                println("POSTHOC_JSON " + mapper.writeValueAsString(mapOf(
                    "input" to body, "status" to response.status, "queue_calls" to calls,
                )))
            } finally {
                context.close()
            }
        }
    }
}
