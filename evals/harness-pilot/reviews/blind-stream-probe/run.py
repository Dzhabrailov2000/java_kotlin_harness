#!/usr/bin/env python3
import json
import subprocess
import tempfile
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parent.parent
PACKETS = ("P13", "P17", "P25", "P28")
SOURCE_PATH = "src/main/java/pilot/CatalogReader.java"
JAVA_FLAG = "-Djava.util.concurrent.ForkJoinPool.common.parallelism=2"

CONTROL = """package pilot;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;
public final class CatalogReader {
    public List<String> read(Supplier<Stream<String>> source, int limit) {
        if (limit < 0) throw new IllegalArgumentException("limit must be non-negative");
        if (limit == 0) return List.of();
        try (Stream<String> stream = source.get()) {
            return stream.map(String::trim).filter(line -> !line.isEmpty()).limit(limit).toList();
        }
    }
}
"""

def capture(command, timeout):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command}\n{result.stdout}")
    return result.stdout

packets = {packet: json.loads((ROOT / "blind" / f"{packet}.json").read_text()) for packet in PACKETS}
original = packets["P13"]["original"][SOURCE_PATH]
assert all(packet["original"][SOURCE_PATH] == original for packet in packets.values())
variants = [("ORIGINAL", original), ("CONTROL_TWR_LIMIT", CONTROL)]
variants.extend((packet, packets[packet]["submitted"][SOURCE_PATH]) for packet in PACKETS)
output = ["Local probe; candidate snapshots are copied without modification.\n",
          capture(["java", "-version"], 10), capture(["javac", "-version"], 10),
          f"JVM flag: {JAVA_FLAG}\nParallel trials per case: 10\n"]
for name, source in variants:
    with tempfile.TemporaryDirectory(prefix="blind-stream-proof-") as directory:
        target = Path(directory)
        candidate = target / "pilot" / "CatalogReader.java"
        candidate.parent.mkdir()
        candidate.write_text(source)
        compilation = capture(["javac", "-d", str(target), str(candidate),
                               str(EVIDENCE / "BlindStreamProbe.java")], 30)
        run_output = capture(["java", JAVA_FLAG, "-cp", str(target), "BlindStreamProbe"], 30)
        output.append(f"\n{name}\ncompile_exit=0\n{compilation}{run_output}run_exit=0\n")
result = "".join(output)
print(result, end="")
