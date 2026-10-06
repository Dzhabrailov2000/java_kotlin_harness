package pilot;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
class CatalogReaderTest {
  @Test void closesSuccessfulReadAndStopsEarly() {
    AtomicInteger closed=new AtomicInteger();AtomicInteger visited=new AtomicInteger();
    var got=new CatalogReader().read(() -> Stream.generate(() -> {visited.incrementAndGet();return " x ";}).onClose(closed::incrementAndGet),3);
    assertEquals(List.of("x","x","x"),got);assertEquals(3,visited.get());assertEquals(1,closed.get());
  }
  @Test void filtersAfterTrim() { assertEquals(List.of("a", Character.toString(0x2003), "b"),new CatalogReader().read(() -> Stream.of("   ", Character.toString(0), " a ", Character.toString(0x2003), "b", "c"),3)); }
  @Test void doesNotOpenForZeroOrInvalidLimit() {
    AtomicInteger opens=new AtomicInteger();
    java.util.function.Supplier<Stream<String>> source=() -> {opens.incrementAndGet();return Stream.of("x");};
    assertEquals(List.of(),new CatalogReader().read(source,0));
    assertThrows(IllegalArgumentException.class,() -> new CatalogReader().read(source,-1));assertEquals(0,opens.get());
  }
  @Test void preservesPrimaryFailureAndSuppressesCloseFailure() {
    var primary=new IllegalStateException("iterate");var closing=new IllegalArgumentException("close");
    var actual=assertThrows(IllegalStateException.class,() -> new CatalogReader().read(() -> Stream.<String>generate(() -> {throw primary;}).onClose(() -> {throw closing;}),1));
    assertSame(primary,actual);assertArrayEquals(new Throwable[]{closing},actual.getSuppressed());
  }
}
