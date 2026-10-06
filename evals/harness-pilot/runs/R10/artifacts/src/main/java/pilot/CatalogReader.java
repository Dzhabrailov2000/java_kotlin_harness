package pilot;
import java.io.*;
import java.util.*;
import java.util.function.Supplier;
import java.util.stream.Stream;
public final class CatalogReader {
  public List<String> read(Supplier<Stream<String>> source, int limit) {
    if (limit < 0) throw new IllegalArgumentException("limit must be >= 0: " + limit);
    if (limit == 0) return List.of();
    try (Stream<String> lines = source.get()) {
      // sequential: a parallel pipeline reads past the limit and rethrows worker failures as wrapped copies
      return lines.sequential().map(String::trim).filter(line -> !line.isEmpty()).limit(limit).toList();
    }
  }
}
