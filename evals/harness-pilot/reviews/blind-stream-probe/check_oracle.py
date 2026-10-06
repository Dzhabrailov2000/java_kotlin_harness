#!/usr/bin/env python3
"""Run the supplemental probe against the unchanged frozen reference solution."""
import subprocess
import tempfile
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parent.parent
source = ROOT / 'tasks/T04/oracle/src/main/java/pilot/CatalogReader.java'

with tempfile.TemporaryDirectory(prefix='pilot-stream-oracle-') as directory:
    commands = [
        ['java', '-version'],
        ['javac', '-version'],
        ['javac', '-d', directory, str(source), str(EVIDENCE / 'BlindStreamProbe.java')],
        ['java', '-Djava.util.concurrent.ForkJoinPool.common.parallelism=2',
         '-cp', directory, 'BlindStreamProbe'],
    ]
    for command in commands:
        print('COMMAND:', ' '.join(command), flush=True)
        result = subprocess.run(command, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, check=True)
        print(result.stdout, end='', flush=True)
