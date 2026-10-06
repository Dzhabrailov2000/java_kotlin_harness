"""Verify selected library contracts locally. Does not evaluate an LLM or install dependencies."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
CACHE = Path.home() / '.gradle/caches/modules-2/files-2.1'

def jar(group, name, version):
    matches = list((CACHE / group / name / version).glob(f'*/{name}-{version}.jar'))
    if len(matches) != 1:
        raise RuntimeError(f'Required cached artifact unavailable: {group}:{name}:{version}; no download attempted')
    return str(matches[0])

def run(args, expect_success=True):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    if expect_success and result.returncode != 0:
        raise RuntimeError(result.stdout)
    if not expect_success and result.returncode == 0:
        raise RuntimeError('Invalid program unexpectedly compiled')
    return result.stdout

def main():
    with tempfile.TemporaryDirectory(prefix='java-kotlin-skill-check-') as temp:
        target = Path(temp)
        print(run(['java', '--version']).strip())
        run(['javac', '--release', '21', '-d', temp, str(ROOT/'fixtures/JavaBehavior.java')])
        print(run(['java', '-cp', temp, 'JavaBehavior']).strip())
        rejected = run(['javac', '--release', '21', '-d', temp, str(ROOT/'fixtures/InvalidVariance.java')], False)
        if 'copy' not in rejected or 'error' not in rejected:
            raise RuntimeError('Unexpected Java compiler failure: '+rejected)
        print('PASS Java compiler rejects unsafe copy direction')

        version = '2.3.21'
        stdlib = jar('org.jetbrains.kotlin', 'kotlin-stdlib', version)
        annotations = jar('org.jetbrains', 'annotations', '13.0')
        compiler = [jar('org.jetbrains.kotlin', 'kotlin-compiler-embeddable', version), stdlib,
                    jar('org.jetbrains.kotlin', 'kotlin-script-runtime', version),
                    jar('org.jetbrains.kotlin', 'kotlin-reflect', '1.6.10'),
                    jar('org.jetbrains.kotlin', 'kotlin-daemon-embeddable', version),
                    jar('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm', '1.8.0'), annotations]
        runtime = os.pathsep.join([stdlib, annotations,
                                  jar('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm', '1.10.2')])
        command = ['java', '-cp', os.pathsep.join(compiler), 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                   '-no-stdlib', '-no-reflect', '-jvm-target', '21', '-classpath', runtime]
        print('Kotlin compiler 2.3.21; coroutine runtime 1.10.2; cached artifacts only')
        run(command + ['-d', str(target/'kotlin'), str(ROOT/'fixtures/KotlinBehavior.kt')])
        print(run(['java', '-cp', os.pathsep.join([str(target/'kotlin'), runtime]), 'KotlinBehaviorKt']).strip())
        rejected = run(command + ['-d', str(target/'invalid'), str(ROOT/'fixtures/InvalidIds.kt')], False)
        if 'CustomerId' not in rejected or 'OrderId' not in rejected or 'error' not in rejected:
            raise RuntimeError('Unexpected Kotlin compiler failure: '+rejected)
        print('PASS Kotlin compiler rejects distinct value-class identifiers')
        print('All 30 focused checks passed; no model or Spring/database integration was evaluated.')

if __name__ == '__main__':
    main()
