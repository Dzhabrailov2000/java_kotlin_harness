package pilot;
import java.io.*;
import java.util.*;
import java.util.function.Supplier;
import java.util.stream.Stream;
public final class CatalogReader {
  public List<String> read(Supplier<Stream<String>> source, int limit) {
    return source.get().filter(line -> !line.isBlank()).map(String::trim).limit(limit).toList();
  }
}
