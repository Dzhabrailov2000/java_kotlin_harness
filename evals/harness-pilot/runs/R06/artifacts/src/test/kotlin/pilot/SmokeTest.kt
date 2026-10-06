package pilot
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Assertions.assertTrue
class SmokeTest { @Test fun `runtime starts`() { assertTrue(System.getProperty("java.version").isNotBlank()) } }
