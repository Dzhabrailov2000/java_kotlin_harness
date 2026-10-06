import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.*;

public class JavaBehavior {
    private static int passed;
    private static volatile int counter;
    record Names(List<String> values) {
        Names { values = List.copyOf(values); }
    }
    static final class Resource implements AutoCloseable {
        boolean closed;
        public void close() { closed = true; throw new IllegalStateException("close"); }
    }
    private static void verify(boolean condition, String name) {
        if (!condition) throw new AssertionError(name);
        passed++;
        System.out.println("PASS " + name);
    }
    public static void main(String[] args) throws Exception {
        var calls = new AtomicInteger();
        Optional<String> value = Optional.of("present");
        value.orElseGet(() -> { calls.incrementAndGet(); return "fallback"; });
        verify(calls.get() == 0, "Optional supplier is lazy");
        value.orElse(Integer.toString(calls.incrementAndGet()));
        verify(calls.get() == 1, "Optional argument is eager");

        var original = new ArrayList<>(List.of("a", "a"));
        var names = new Names(original);
        original.clear();
        boolean unmodifiable = false;
        try { names.values().add("b"); }
        catch (UnsupportedOperationException expected) { unmodifiable = true; }
        verify(names.values().equals(List.of("a", "a")) && unmodifiable,
            "List.copyOf snapshot preserves duplicates and blocks mutation");

        BigDecimal a = new BigDecimal("2.0"), b = new BigDecimal("2.00");
        verify(!a.equals(b) && a.compareTo(b) == 0 && new HashSet<>(List.of(a, b)).size() == 2,
            "BigDecimal equality differs from numeric ordering");

        List<Number> target = new ArrayList<>(List.of(0, 0));
        Collections.copy(target, List.of(3, 4));
        boolean sizeRejected = false;
        try { Collections.copy(new ArrayList<Number>(10), List.of(3)); }
        catch (IndexOutOfBoundsException expected) { sizeRejected = true; }
        verify(target.equals(List.of(3, 4)) && sizeRejected,
            "Generic copy accepts variance but requires size, not capacity");

        boolean duplicatesRejected = false;
        try { Stream.of("apple", "apricot").collect(Collectors.toMap(s -> s.charAt(0), s -> s)); }
        catch (IllegalStateException expected) { duplicatesRejected = true; }
        verify(duplicatesRejected, "toMap does not silently choose a duplicate winner");

        Resource resource = new Resource();
        boolean originalPreserved = false;
        try (resource) { throw new IllegalArgumentException("body"); }
        catch (IllegalArgumentException e) {
            originalPreserved = e.getSuppressed().length == 1
                && e.getSuppressed()[0] instanceof IllegalStateException;
        }
        verify(resource.closed && originalPreserved, "Cleanup preserves original failure");

        var path = Files.createTempFile("harness-lines-", ".txt");
        try {
            Files.writeString(path, "a\n\nb\n", StandardCharsets.UTF_8);
            long count;
            try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
                count = lines.filter(line -> !line.isBlank()).count();
            }
            verify(count == 2, "I/O stream is consumed within resource scope");
        } finally { Files.delete(path); }

        var barrier = new CyclicBarrier(2);
        counter = 0;
        try (var pool = Executors.newFixedThreadPool(2)) {
            Callable<Void> readThenWrite = () -> {
                int before = counter;
                barrier.await(5, TimeUnit.SECONDS);
                counter = before + 1;
                return null;
            };
            for (var task : pool.invokeAll(List.of(readThenWrite, readThenWrite))) task.get();
        }
        verify(counter == 1, "Volatile cannot make read-modify-write atomic");

        var atomic = new AtomicInteger();
        try (var pool = Executors.newFixedThreadPool(2)) {
            Callable<Void> increment = () -> { for (int i = 0; i < 1000; i++) atomic.incrementAndGet(); return null; };
            for (var task : pool.invokeAll(List.of(increment, increment))) task.get();
        }
        verify(atomic.get() == 2000, "Atomic counter preserves concurrent increments");

        verify(!new BigDecimal(0.1).equals(new BigDecimal("0.1")),
            "Decimal from binary double differs from exact decimal input");
        boolean repeatingRejected = false;
        try { BigDecimal.ONE.divide(new BigDecimal("3")); }
        catch (ArithmeticException expected) { repeatingRejected = true; }
        verify(repeatingRejected
            && BigDecimal.ONE.divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP).equals(new BigDecimal("0.33")),
            "Non-terminating decimal division needs an explicit rounding contract");
        boolean overflowRejected = false;
        try { Math.addExact(Integer.MAX_VALUE, 1); }
        catch (ArithmeticException expected) { overflowRejected = true; }
        verify(overflowRejected && Integer.MAX_VALUE + 1 == Integer.MIN_VALUE,
            "Checked arithmetic distinguishes overflow from wrapped integer result");

        var berlin = ZoneId.of("Europe/Berlin");
        var clock = Clock.fixed(Instant.parse("2024-03-30T11:00:00Z"), berlin);
        var start = ZonedDateTime.now(clock);
        verify(start.plusDays(1).getHour() == 12 && start.plusHours(24).getHour() == 13
            && Duration.between(start, start.plusDays(1)).toHours() == 23,
            "Calendar day and 24-hour duration differ at a DST transition");
        verify(berlin.getRules().getValidOffsets(LocalDateTime.of(2024, 3, 31, 2, 30)).isEmpty()
            && berlin.getRules().getValidOffsets(LocalDateTime.of(2024, 10, 27, 2, 30)).size() == 2,
            "Local time can have no offset in a gap or two offsets in an overlap");
        verify(Currency.getInstance("JPY").getDefaultFractionDigits() == 0
            && Currency.getInstance("EUR").getDefaultFractionDigits() == 2
            && Currency.getInstance("XDR").getDefaultFractionDigits() == -1,
            "Currency fraction digits are not universally two");
        System.out.println("JAVA_CHECKS=" + passed);
    }
}
