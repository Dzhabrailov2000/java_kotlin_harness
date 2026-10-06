import pilot.CatalogReader;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public final class BlindStreamProbe {
    private static final int PARALLEL_TRIALS = 10;

    public static void main(String[] args) {
        CatalogReader reader = new CatalogReader();
        checkEarlyLimits(reader);
        checkTrim(reader);
        checkInfiniteSequentialSource(reader);
        checkTraversalAndCloseFailure(reader);
        checkCloseFailure(reader);
        checkParallelPrefix(reader);
        checkParallelException(reader);
    }

    private static void checkEarlyLimits(CatalogReader reader) {
        for (int limit : new int[] {-1, 0}) {
            AtomicInteger opened = new AtomicInteger();
            try {
                List<String> result = reader.read(() -> {
                    opened.incrementAndGet();
                    throw new AssertionError("source unexpectedly opened");
                }, limit);
                System.out.println("early_limit=" + limit + " result=" + result + " opened=" + opened.get());
            } catch (Throwable actual) {
                System.out.println("early_limit=" + limit + " threw=" + actual.getClass().getSimpleName() + " opened=" + opened.get());
            }
        }
    }

    private static void checkTrim(CatalogReader reader) {
        String nul = String.valueOf((char) 0);
        String emSpace = String.valueOf((char) 0x2003);
        AtomicInteger closed = new AtomicInteger();
        List<String> result = reader.read(() -> Stream.of(nul, emSpace, " x ", " x ")
            .onClose(closed::incrementAndGet), 3);
        System.out.println("trim_contract=" + result.equals(List.of(emSpace, "x", "x"))
            + " code_points=" + result.stream().map(text -> text.codePoints().boxed().toList()).toList()
            + " closed=" + closed.get());
    }

    private static void checkInfiniteSequentialSource(CatalogReader reader) {
        AtomicInteger read = new AtomicInteger();
        AtomicInteger closed = new AtomicInteger();
        List<String> result = reader.read(() -> Stream.generate(() -> {
            int index = read.incrementAndGet();
            return index % 2 == 1 ? " " : " x ";
        }).onClose(closed::incrementAndGet), 3);
        System.out.println("infinite_sequential=" + result + " read=" + read.get() + " closed=" + closed.get());
    }

    private static void checkTraversalAndCloseFailure(CatalogReader reader) {
        IllegalStateException traversal = new IllegalStateException("traversal");
        IllegalStateException closing = new IllegalStateException("closing");
        AtomicInteger closed = new AtomicInteger();
        try {
            reader.read(() -> Stream.<String>generate(() -> { throw traversal; })
                .onClose(() -> { closed.incrementAndGet(); throw closing; }), 1);
            System.out.println("sequential_error=NO_EXCEPTION closed=" + closed.get());
        } catch (Throwable actual) {
            System.out.println("sequential_error_same=" + (actual == traversal)
                + " suppressed_close=" + onlySuppressed(actual, closing) + " closed=" + closed.get());
        }
    }

    private static void checkCloseFailure(CatalogReader reader) {
        IllegalStateException closing = new IllegalStateException("close-only");
        AtomicInteger closed = new AtomicInteger();
        try {
            List<String> result = reader.read(() -> Stream.of(" x ")
                .onClose(() -> { closed.incrementAndGet(); throw closing; }), 1);
            System.out.println("close_only_returned=" + result + " closed=" + closed.get());
        } catch (Throwable actual) {
            System.out.println("close_error_same=" + (actual == closing) + " closed=" + closed.get());
        }
    }

    private static void checkParallelPrefix(CatalogReader reader) {
        int returnedExpected = 0;
        int threw = 0;
        int closedTotal = 0;
        String firstThrown = "none";
        for (int trial = 0; trial < PARALLEL_TRIALS; trial++) {
            AtomicInteger closed = new AtomicInteger();
            IllegalStateException tailError = new IllegalStateException("after-prefix");
            try {
                List<String> result = reader.read(() -> IntStream.range(0, 8192).parallel()
                    .mapToObj(index -> {
                        if (index == 0) return " value ";
                        throw tailError;
                    }).onClose(closed::incrementAndGet), 1);
                if (result.equals(List.of("value"))) returnedExpected++;
            } catch (Throwable actual) {
                threw++;
                if (firstThrown.equals("none")) firstThrown = actual.getClass().getSimpleName() + ":" + actual.getMessage();
            }
            closedTotal += closed.get();
        }
        System.out.println("parallel_prefix trials=" + PARALLEL_TRIALS + " returned_expected=" + returnedExpected
            + " threw=" + threw + " closed=" + closedTotal + " first_thrown=" + firstThrown);
    }

    private static void checkParallelException(CatalogReader reader) {
        int originalThrown = 0;
        int originalInCause = 0;
        int closeSuppressedOnThrown = 0;
        int closeSuppressedOnOriginal = 0;
        int closedTotal = 0;
        int workerThrows = 0;
        String firstExample = "none";
        for (int trial = 0; trial < PARALLEL_TRIALS; trial++) {
            IllegalStateException traversal = new IllegalStateException("parallel-traversal");
            IllegalStateException closing = new IllegalStateException("parallel-closing");
            AtomicReference<String> throwThread = new AtomicReference<>();
            AtomicInteger closed = new AtomicInteger();
            try {
                reader.read(() -> IntStream.range(0, 8192).parallel()
                    .mapToObj(index -> {
                        if (index == 0) {
                            throwThread.set(Thread.currentThread().getName());
                            throw traversal;
                        }
                        return "value";
                    }).onClose(() -> { closed.incrementAndGet(); throw closing; }), 1);
            } catch (Throwable actual) {
                if (actual == traversal) originalThrown++;
                if (actual.getCause() == traversal) originalInCause++;
                if (onlySuppressed(actual, closing)) closeSuppressedOnThrown++;
                if (onlySuppressed(traversal, closing)) closeSuppressedOnOriginal++;
                if (throwThread.get() != null && throwThread.get().startsWith("ForkJoinPool.")) workerThrows++;
                if (firstExample.equals("none")) {
                    firstExample = "same=" + (actual == traversal) + ",class=" + actual.getClass().getSimpleName()
                        + ",message=" + actual.getMessage() + ",cause_same=" + (actual.getCause() == traversal)
                        + ",throw_thread=" + throwThread.get();
                }
            }
            closedTotal += closed.get();
        }
        System.out.println("parallel_error trials=" + PARALLEL_TRIALS + " original_thrown=" + originalThrown
            + " original_in_cause=" + originalInCause + " close_suppressed_on_thrown=" + closeSuppressedOnThrown
            + " close_suppressed_on_original=" + closeSuppressedOnOriginal + " closed=" + closedTotal
            + " worker_throws=" + workerThrows);
        System.out.println("parallel_error_first " + firstExample);
    }

    private static boolean onlySuppressed(Throwable actual, Throwable expected) {
        return actual.getSuppressed().length == 1 && actual.getSuppressed()[0] == expected;
    }
}
