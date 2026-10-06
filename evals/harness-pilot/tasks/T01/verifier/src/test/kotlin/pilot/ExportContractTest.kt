package pilot
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.*
import org.springframework.test.web.servlet.setup.MockMvcBuilders
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.http.MediaType
import tools.jackson.databind.json.JsonMapper
@org.springframework.context.annotation.Configuration(proxyBeanMethods=false)
@org.springframework.web.servlet.config.annotation.EnableWebMvc
@org.springframework.context.annotation.ComponentScan(basePackages=["pilot"])
class FixtureWebConfig
class ExportContractTest {
  private val mapper = JsonMapper.builder().build()
  private fun request(body: String, queue: ExportQueue): org.springframework.mock.web.MockHttpServletResponse {
    val context = org.springframework.web.context.support.AnnotationConfigWebApplicationContext()
    context.servletContext = org.springframework.mock.web.MockServletContext()
    context.register(FixtureWebConfig::class.java)
    context.addBeanFactoryPostProcessor { factory -> factory.registerSingleton("fixtureExportQueue", queue) }
    context.refresh()
    try {
      return MockMvcBuilders.webAppContextSetup(context).build()
        .perform(post("/exports").contentType(MediaType.APPLICATION_JSON).content(body)).andReturn().response
    } finally { context.close() }
  }
  @Test fun `accepted means queued only and uses normalized account`() {
    val calls=mutableListOf<Pair<String,String>>()
    val q=object:ExportQueue { override fun enqueue(accountId:String,format:String):String { calls.add(accountId to format); return "job-17" } }
    for (format in listOf("csv","json")) {
      calls.clear()
      val r=request("""{"accountId":"  account-2  ","format":"$format"}""",q)
      assertEquals(202,r.status); assertEquals("/exports/job-17",r.getHeader("Location"))
      val body=mapper.readTree(r.contentAsString);assertEquals("job-17",body.get("id").asString());assertEquals("pending",body.get("state").asString())
      assertEquals(listOf("account-2" to format),calls)
    }
  }
  @Test fun `invalid request never queues`() {
    var calls=0
    val q=object:ExportQueue { override fun enqueue(accountId:String,format:String):String { calls++;return "job-1" } }
    for(body in listOf("""{"accountId":" ","format":"csv"}""","""{"accountId":"a","format":"xml"}""","{}","""{"accountId":null,"format":"csv"}""","[")) {
      assertEquals(400,request(body,q).status,body)
    }
    assertEquals(0,calls)
  }
  @Test fun `queue outage does not disclose internal details`() {
    val q=object:ExportQueue { override fun enqueue(accountId:String,format:String):String { throw QueueUnavailableException("internal-secret-marker") } }
    val r=request("""{"accountId":"a","format":"csv"}""",q)
    assertEquals(503,r.status);assertFalse(r.contentAsString.contains("internal-secret-marker"))
  }
}
