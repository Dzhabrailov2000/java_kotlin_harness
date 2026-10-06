package pilot;
import java.util.*;
import java.util.function.Supplier;
import java.util.stream.Stream;
public final class CatalogReader {
  public List<String> read(Supplier<Stream<String>> source,int limit) {
    if(limit<0)throw new IllegalArgumentException("negative limit");
    if(limit==0)return List.of();
    try(var lines=source.get()) { return lines.map(String::trim).filter(line -> !line.isEmpty()).limit(limit).toList(); }
  }
}
