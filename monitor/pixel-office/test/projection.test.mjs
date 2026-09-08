/**
 * What the office is allowed to say about recorded evidence.
 *
 * Every record below is a FIXTURE written by this test file. No CLI, no model and no browser takes
 * part: these are the shapes run_progress.py validates, replayed to check the mapping from evidence
 * to captions. Nothing here is, or may be presented as, a live task.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  IMPLEMENTER,
  MANAGER,
  STALE_MS,
  USER,
  emptyJournalFold,
  emptyTraceFold,
  foldJournal,
  foldTrace,
  projectOffice,
} from '../src/projection.mjs';

const NOW = Date.parse('2026-09-08T12:00:00.000Z');

function at(secondsAgo) {
  return new Date(NOW - secondsAgo * 1000).toISOString().replace(/(\.\d{3})\d*Z$/, '$1Z');
}

let sequence = 0;
function record(fields) {
  sequence += 1;
  return {
    schema: 1,
    event_id: 'fixture' + sequence,
    time: at(10),
    run_id: 'fixture-run',
    attempt: 1,
    step_id: 'build-1',
    source: 'launcher',
    phase: 'build',
    event: 'run',
    status: 'started',
    ...fields,
  };
}

function traceRecord(fields) {
  sequence += 1;
  return {
    schema: 1,
    capture: 'trace/1',
    record_id: 'fixturetrace' + sequence,
    time: at(10),
    run_id: 'fixture-run',
    attempt: 1,
    step_id: 'build-1',
    source: 'launcher',
    kind: 'status',
    phase: 'build',
    ...fields,
  };
}

function project(journalRecords, traceRecords = [], now = NOW, source = { available: true, detail: '' }) {
  const journal = foldJournal(journalRecords, emptyJournalFold());
  return projectOffice({
    journal,
    // The adapter seeds the trace with the run the journal selected; the fixtures do the same.
    trace: foldTrace(traceRecords, emptyTraceFold(), journal.runId),
    now,
    source,
  });
}

const LAUNCH = record({ event: 'run', status: 'started', model: 'claude-opus-5', effort: 'xhigh' });

test('a requested launch is not observed work', () => {
  const state = project([LAUNCH]);
  assert.equal(state.actors[IMPLEMENTER].state, 'idle');
  assert.match(state.actors[IMPLEMENTER].caption, /запуск запрошен/);
  assert.equal(state.actors[IMPLEMENTER].toolName, undefined);
});

test('an observed tool call is work, and its result ends it', () => {
  const working = project([LAUNCH, record({ source: 'native', event: 'tool_call', status: 'observed', tool: 'Bash', component: 'git', call_id: 'c1' })]);
  assert.equal(working.actors[IMPLEMENTER].state, 'working');
  assert.equal(working.actors[IMPLEMENTER].caption, 'Bash (git)');
  assert.equal(working.actors[IMPLEMENTER].toolName, 'Bash');
  assert.equal(working.actors[IMPLEMENTER].provenance, 'попытка 1 · build-1');

  const done = project([
    LAUNCH,
    record({ source: 'native', event: 'tool_call', status: 'observed', tool: 'Bash', call_id: 'c1' }),
    record({ source: 'native', event: 'tool_result', status: 'returned', tool: 'Bash', call_id: 'c1' }),
  ]);
  assert.equal(done.actors[IMPLEMENTER].state, 'working');
  assert.equal(done.actors[IMPLEMENTER].caption, 'модель отвечает');
});

test('silence past the deadline stops claiming work and never becomes a success', () => {
  const stale = project([
    record({ time: at(STALE_MS / 1000 + 60), event: 'run', status: 'started' }),
    record({ time: at(STALE_MS / 1000 + 30), source: 'native', event: 'tool_call', status: 'observed', tool: 'Read', call_id: 'c9' }),
  ]);
  assert.equal(stale.actors[IMPLEMENTER].state, 'stale');
  assert.match(stale.actors[IMPLEMENTER].caption, /тишина \d+ мин/);
});

test('a rate limit retry is waiting, not work', () => {
  const state = project(
    [LAUNCH, record({ source: 'native', event: 'tool_call', status: 'observed', tool: 'Bash', call_id: 'c1' })],
    [traceRecord({ kind: 'status', state: 'api_retry', attempt_no: 2, retry_delay_ms: 4000 })],
  );
  assert.equal(state.actors[IMPLEMENTER].state, 'waiting');
  assert.match(state.actors[IMPLEMENTER].caption, /повтор запроса к API \(попытка 2\)/);
});

test('a retry ends as soon as the invocation is observed again', () => {
  // The producer records status/api_retry and then goes on: a later tool call of the same
  // step is the model answering, so the office may not still be showing the wait.
  const resumed = project(
    [LAUNCH, record({ time: at(5), source: 'native', event: 'tool_call', status: 'observed', tool: 'Read', call_id: 'c5' })],
    [traceRecord({ time: at(30), kind: 'status', state: 'api_retry', attempt_no: 2, retry_delay_ms: 4000 })],
  );
  assert.equal(resumed.actors[IMPLEMENTER].state, 'working');
  assert.equal(resumed.actors[IMPLEMENTER].caption, 'Read');

  // The same through the other feed: a public response recorded after the retry ends it too.
  const answered = project(
    [LAUNCH],
    [traceRecord({ time: at(30), kind: 'status', state: 'api_retry', attempt_no: 2, retry_delay_ms: 4000 }),
     traceRecord({ time: at(5), kind: 'message', message_kind: 'response', role: 'claude' })],
  );
  assert.notEqual(answered.actors[IMPLEMENTER].state, 'waiting');
  assert.doesNotMatch(answered.actors[IMPLEMENTER].caption, /повтор/);
});

test('a retry nobody confirmed becomes silence instead of waiting forever', () => {
  const abandoned = project(
    [record({ time: at(600), event: 'run', status: 'started' })],
    [traceRecord({ time: at(590), kind: 'status', state: 'api_retry', attempt_no: 2, retry_delay_ms: 1000 })],
  );
  assert.equal(abandoned.actors[IMPLEMENTER].state, 'stale');
  assert.match(abandoned.actors[IMPLEMENTER].caption, /повтор запроса к API не подтвержден/);
  assert.match(abandoned.actors[IMPLEMENTER].caption, /тишина \d+ мин/);
});

test('a terminal turn outcome ends the work claim even when a tool result was lost', () => {
  const success = project([
    LAUNCH,
    record({ time: at(200), source: 'native', event: 'tool_call', status: 'observed', tool: 'Read', call_id: 'lost' }),
    record({ time: at(5), source: 'native', event: 'cli_result', status: 'success' }),
  ]);
  assert.equal(success.actors[IMPLEMENTER].state, 'idle');
  assert.equal(success.actors[IMPLEMENTER].caption, 'ход CLI завершен, процесс еще не вышел');

  const failed = project([
    LAUNCH,
    record({ time: at(200), source: 'native', event: 'tool_call', status: 'observed', tool: 'Read', call_id: 'lost' }),
    record({ time: at(5), source: 'native', event: 'cli_result', status: 'error' }),
  ]);
  assert.equal(failed.actors[IMPLEMENTER].state, 'error');
  assert.equal(failed.actors[IMPLEMENTER].caption, 'CLI сообщил об ошибке хода');

  // A call started after that outcome is newer evidence and keeps its own state.
  const again = project([
    LAUNCH,
    record({ time: at(30), source: 'native', event: 'cli_result', status: 'success' }),
    record({ time: at(5), source: 'native', event: 'tool_call', status: 'observed', tool: 'Bash', call_id: 'after' }),
  ]);
  assert.equal(again.actors[IMPLEMENTER].state, 'working');
  assert.equal(again.actors[IMPLEMENTER].caption, 'Bash');
});

test('the end of one invocation does not end another that is still fresh', () => {
  const state = project([
    record({ step_id: 'build-1', event: 'run', status: 'started' }),
    record({ step_id: 'build-1', source: 'native', event: 'tool_call', status: 'observed', tool: 'Edit', call_id: 'a1' }),
    record({ step_id: 'build-2', event: 'run', status: 'started' }),
    record({ step_id: 'build-2', source: 'native', event: 'cli_result', status: 'success' }),
    record({ step_id: 'build-2', event: 'cli_exit', status: 'exited', exit_code: 0 }),
  ]);
  assert.equal(state.actors[IMPLEMENTER].state, 'working');
  assert.equal(state.actors[IMPLEMENTER].caption, 'Edit');
});

test('a terminal turn in one invocation does not hide fresh work in another before that process exits', () => {
  // The interval the office used to get wrong: build-b's CLI has reported the outcome of its
  // turn, but the process has not exited yet, while build-a is four seconds into an Edit.
  const before = [
    record({ time: at(14), step_id: 'active-a', event: 'run', status: 'started' }),
    record({ time: at(9), step_id: 'ending-b', event: 'run', status: 'started' }),
    record({ time: at(4), step_id: 'active-a', source: 'native', event: 'tool_call', status: 'observed', tool: 'Edit', call_id: 'a-edit' }),
    record({ time: at(3), step_id: 'ending-b', source: 'native', event: 'tool_call', status: 'observed', tool: 'Read', call_id: 'b-read' }),
  ];
  for (const outcome of ['success', 'error']) {
    const ending = record({ time: at(2), step_id: 'ending-b', source: 'native', event: 'cli_result', status: outcome });
    const state = project([...before, ending]);
    assert.equal(state.actors[IMPLEMENTER].state, 'working', 'the turn of ending-b ended the work of active-a');
    assert.equal(state.actors[IMPLEMENTER].caption, 'Edit');
    assert.match(state.actors[IMPLEMENTER].provenance, /попытка 1 · active-a/);
    assert.match(state.actors[IMPLEMENTER].provenance, /2 параллельных сессии/);
    // The incremental fold of a poll sees exactly what a fold of the whole journal does.
    const fold = foldJournal([ending], foldJournal(before, emptyJournalFold()));
    assert.deepEqual(projectOffice({ journal: fold, trace: emptyTraceFold(), now: NOW }).actors, state.actors);
  }

  // The controls this correction may not break: work that stopped being observed is not
  // resurrected by the invocation beside it ending cleanly, and two ended turns stay idle.
  const exited = [...before,
    record({ time: at(2), step_id: 'ending-b', source: 'native', event: 'cli_result', status: 'success' }),
    record({ time: at(1), step_id: 'ending-b', event: 'cli_exit', status: 'exited', exit_code: 0 })];
  assert.equal(project(exited).actors[IMPLEMENTER].caption, 'Edit');
  const abandoned = project(exited, [], NOW + STALE_MS + 1000);
  assert.equal(abandoned.actors[IMPLEMENTER].state, 'stale', 'a clean exit beside abandoned work is not the state of the role');
  assert.match(abandoned.actors[IMPLEMENTER].provenance, /active-a/);
  assert.doesNotMatch(abandoned.actors[IMPLEMENTER].provenance, /параллельных/);
  const bothEnded = project([...before,
    record({ time: at(2), step_id: 'ending-b', source: 'native', event: 'cli_result', status: 'success' }),
    record({ time: at(1), step_id: 'active-a', source: 'native', event: 'cli_result', status: 'success' })]);
  assert.equal(bothEnded.actors[IMPLEMENTER].state, 'idle');
});

test('an abandoned invocation and its old receipt never hide a newer failed attempt', () => {
  const orphan = [
    record({ time: at(601), phase: 'review', step_id: 'orphan-review-a1', event: 'run', status: 'started' }),
    record({ time: at(600), phase: 'review', step_id: 'orphan-review-a1', source: 'native', event: 'tool_call',
             status: 'observed', tool: 'Read', call_id: 'old-open-read' }),
  ];
  const passed = record({ time: at(541), source: 'receipt', phase: 'review', event: 'phase', status: 'passed',
                          evidence: 'v'.repeat(64) });
  const failed = [
    record({ time: at(2), attempt: 2, phase: 'review', step_id: 'failed-review-a2', event: 'run', status: 'started' }),
    record({ time: at(1), attempt: 2, phase: 'review', step_id: 'failed-review-a2', event: 'cli_exit', status: 'launch_error' }),
  ];
  const state = project([...orphan, passed, ...failed]);
  assert.equal(state.actors[MANAGER].state, 'error');
  assert.match(state.actors[MANAGER].caption, /CLI не запустился/);
  assert.doesNotMatch(state.actors[MANAGER].caption, /PASS/);
  assert.match(state.actors[MANAGER].provenance, /попытка 2 · failed-review-a2/);
  assert.equal(state.attempt, 2);
  const incremental = foldJournal([...failed], foldJournal([...orphan, passed], emptyJournalFold()));
  assert.deepEqual(projectOffice({ journal: incremental, trace: emptyTraceFold(), now: NOW }).actors, state.actors);

  // Without the receipt the newer failure is the state anyway: the silence of an abandoned
  // attempt-1 session is not what this role is doing now.
  const withoutReceipt = project([...orphan, ...failed]);
  assert.equal(withoutReceipt.actors[MANAGER].state, 'error');
  assert.match(withoutReceipt.actors[MANAGER].provenance, /попытка 2/);
  // Giving the old session its exit changes nothing, and the old receipt stays readable as
  // the current caption while it is still the latest word about the role.
  const closed = project([...orphan, record({ time: at(570), phase: 'review', step_id: 'orphan-review-a1', event: 'cli_exit', status: 'exited', exit_code: 0 }), passed, ...failed]);
  assert.equal(closed.actors[MANAGER].state, 'error');
  const history = project([...orphan, record({ time: at(570), phase: 'review', step_id: 'orphan-review-a1', event: 'cli_exit', status: 'exited', exit_code: 0 }), passed]);
  assert.equal(history.actors[MANAGER].caption, 'ревью: PASS');
  assert.match(history.actors[MANAGER].provenance, /попытка 1/);

  // The same masking inside one attempt: the receipt is older than the failure recorded
  // after it, so it is not the current word about this role even though the abandoned
  // session the office shows is older still. Silence stays silence, never an old PASS.
  const sameAttempt = project([...orphan, passed,
    record({ time: at(2), phase: 'review', step_id: 'second-review-a1', event: 'run', status: 'started' }),
    record({ time: at(1), phase: 'review', step_id: 'second-review-a1', event: 'cli_exit', status: 'launch_error' })]);
  assert.equal(sameAttempt.actors[MANAGER].state, 'stale');
  assert.match(sameAttempt.actors[MANAGER].caption, /тишина \d+ мин/);
  assert.doesNotMatch(sameAttempt.actors[MANAGER].caption, /PASS/);
});

test('a timeout is an error and a non-zero exit is an error', () => {
  const timedOut = project([LAUNCH, record({ event: 'cli_exit', status: 'timeout', exit_code: -15 })]);
  assert.equal(timedOut.actors[IMPLEMENTER].state, 'error');
  assert.match(timedOut.actors[IMPLEMENTER].caption, /таймаут/);
  const failed = project([LAUNCH, record({ event: 'cli_exit', status: 'exited', exit_code: 2 })]);
  assert.equal(failed.actors[IMPLEMENTER].state, 'error');
});

test('a finished build waits for the manager; a read-only handoff is a delivered report', () => {
  const build = project([
    LAUNCH,
    record({ event: 'cli_exit', status: 'exited', exit_code: 0 }),
    record({ event: 'result', status: 'ready' }),
  ]);
  assert.equal(build.actors[IMPLEMENTER].state, 'idle');
  assert.equal(build.actors[IMPLEMENTER].caption, 'сборка готова к проверке менеджера');

  const handoff = project([
    record({ phase: 'handoff', step_id: 'handoff-1', event: 'run', status: 'started' }),
    record({ phase: 'handoff', step_id: 'handoff-1', event: 'cli_exit', status: 'exited', exit_code: 0 }),
    record({ phase: 'handoff', step_id: 'handoff-1', event: 'result', status: 'ready' }),
  ]);
  assert.equal(handoff.actors[IMPLEMENTER].caption, 'отчет передан');
  assert.equal(handoff.actors[IMPLEMENTER].role, 'Claude · передача отчета');
});

test('the human actor stays neutral and never animates', () => {
  const nothing = project([LAUNCH]);
  assert.equal(nothing.actors[USER].state, 'human');
  assert.equal(nothing.actors[USER].caption, 'запроса в трассировке нет');
  const asked = project([LAUNCH], [traceRecord({ kind: 'message', message_kind: 'user_prompt', role: 'user', title: 'Задача' })]);
  assert.equal(asked.actors[USER].state, 'human');
  assert.equal(asked.actors[USER].caption, 'запрос зарегистрирован');
  // A receipt arriving does not make the person work.
  const receipt = project(
    [LAUNCH, record({ source: 'receipt', phase: 'tests', event: 'phase', status: 'passed', evidence: 'a'.repeat(64), component: 'python', count: 2 })],
    [traceRecord({ kind: 'message', message_kind: 'user_prompt', role: 'user' })],
  );
  assert.equal(receipt.actors[USER].state, 'human');
});

test('a review session belongs to the manager and is named as the independent check', () => {
  const state = project([
    record({ phase: 'review', step_id: 'review-1', event: 'run', status: 'started', model: 'gpt-6-astra' }),
    record({ phase: 'review', step_id: 'review-1', source: 'native', event: 'tool_call', status: 'observed', tool: 'Read', call_id: 'r1' }),
  ]);
  assert.equal(state.actors[MANAGER].state, 'working');
  assert.equal(state.actors[MANAGER].role, 'Codex · независимая проверка');
  assert.equal(state.actors[IMPLEMENTER].state, 'unknown');
});

test('a verified review FAIL is a FAIL even though its own process succeeded', () => {
  const state = project([
    record({ phase: 'review', step_id: 'review-1', event: 'run', status: 'started' }),
    record({ phase: 'review', step_id: 'review-1', source: 'native', event: 'cli_result', status: 'success' }),
    record({ phase: 'review', step_id: 'review-1', event: 'cli_exit', status: 'exited', exit_code: 0 }),
    record({ phase: 'review', step_id: 'review-1', source: 'receipt', event: 'phase', status: 'failed',
             evidence: 'b'.repeat(64), snapshot: 'c'.repeat(64), count: 3 }),
  ]);
  assert.equal(state.actors[MANAGER].state, 'idle');
  assert.equal(state.actors[MANAGER].caption, 'ревью: FAIL');
  assert.match(state.actors[MANAGER].provenance, /из приемочной расписки/);
  assert.match(state.actors[MANAGER].provenance, /evidence bbbbbbbbbbbb/);
});

test('checks aggregate only inside one attempt and one candidate snapshot', () => {
  const snapshot = 'd'.repeat(64);
  const partial = project([
    record({ source: 'receipt', phase: 'tests', event: 'phase', status: 'passed', evidence: 'e'.repeat(64),
             snapshot, component: 'python', count: 3 }),
  ]);
  assert.equal(partial.actors[MANAGER].caption, 'проверки: 1 PASS, из 3, 2 без результата');

  const failing = project([
    record({ source: 'receipt', phase: 'tests', event: 'phase', status: 'passed', evidence: 'e'.repeat(64),
             snapshot, component: 'python', count: 3 }),
    record({ source: 'receipt', phase: 'tests', event: 'phase', status: 'failed', evidence: 'f'.repeat(64),
             snapshot, component: 'browser', count: 3 }),
  ]);
  assert.equal(failing.actors[MANAGER].caption, 'проверки: 1 PASS, 1 FAIL, из 3, 1 без результата');

  // A later candidate tree starts its own aggregate: the earlier PASS is history, not evidence.
  const rebuilt = project([
    record({ source: 'receipt', phase: 'tests', event: 'phase', status: 'passed', evidence: 'e'.repeat(64),
             snapshot, component: 'python', count: 3 }),
    record({ attempt: 2, source: 'receipt', phase: 'tests', event: 'phase', status: 'passed', evidence: 'g'.repeat(64),
             snapshot: 'h'.repeat(64), component: 'python', count: 3 }),
  ]);
  assert.equal(rebuilt.actors[MANAGER].caption, 'проверки: 1 PASS, из 3, 2 без результата');
  assert.match(rebuilt.actors[MANAGER].provenance, /попытка 2/);
});

test('a manager decision is a recorded fact and COMPLETE is never derived from a process', () => {
  const retry = project([record({ source: 'manager', phase: 'decision', step_id: 'decision', event: 'decision', status: 'retry' })]);
  assert.equal(retry.actors[MANAGER].state, 'idle');
  assert.equal(retry.actors[MANAGER].caption, 'решение менеджера: RETRY');

  const complete = project([record({ source: 'manager', phase: 'decision', step_id: 'decision', event: 'decision',
                                     status: 'complete', evidence: 'i'.repeat(64) })]);
  assert.equal(complete.actors[MANAGER].caption, 'решение менеджера: COMPLETE');

  // A successful CLI turn alone says nothing about acceptance.
  const finished = project([
    record({ phase: 'review', step_id: 'review-1', event: 'run', status: 'started' }),
    record({ phase: 'review', step_id: 'review-1', source: 'native', event: 'cli_result', status: 'success' }),
    record({ phase: 'review', step_id: 'review-1', event: 'cli_exit', status: 'exited', exit_code: 0 }),
  ]);
  assert.equal(finished.actors[MANAGER].caption, 'сессия CLI завершена');
  assert.doesNotMatch(finished.actors[MANAGER].caption, /PASS|COMPLETE/);
});

test('registered triage feedback is recorded, and its findings stay uncounted', () => {
  const state = project([], [traceRecord({ kind: 'message', message_kind: 'feedback', role: 'manager', phase: 'triage', step_id: 'triage-1' })]);
  assert.equal(state.actors[MANAGER].state, 'idle');
  assert.equal(state.actors[MANAGER].caption, 'разбор: обратная связь зарегистрирована');
  assert.match(state.actors[MANAGER].provenance, /состав замечаний неизвестен/);
  assert.notEqual(state.triage, null);
});

test('an older recorded result never masks a newer invocation of a later attempt', () => {
  const receipt = record({ time: at(600), source: 'receipt', phase: 'review', event: 'phase', status: 'passed',
                           evidence: 'r'.repeat(64) });
  const failedLaunch = project([
    receipt,
    record({ time: at(300), attempt: 2, phase: 'review', step_id: 'review-2', event: 'run', status: 'started' }),
    record({ time: at(20), attempt: 2, phase: 'review', step_id: 'review-2', event: 'cli_exit', status: 'launch_error' }),
  ]);
  assert.equal(failedLaunch.actors[MANAGER].state, 'error');
  assert.match(failedLaunch.actors[MANAGER].caption, /CLI не запустился/);
  assert.match(failedLaunch.actors[MANAGER].provenance, /попытка 2/);
  assert.doesNotMatch(failedLaunch.actors[MANAGER].caption, /PASS/);

  const silent = project([
    receipt,
    record({ time: at(300), attempt: 2, phase: 'review', step_id: 'review-2', event: 'run', status: 'started' }),
  ]);
  assert.equal(silent.actors[MANAGER].state, 'stale');
  assert.match(silent.actors[MANAGER].provenance, /попытка 2/);

  // The receipt is still the caption while it is the newest thing known about this role.
  const current = project([
    record({ time: at(600), attempt: 1, phase: 'review', step_id: 'review-1', event: 'run', status: 'started' }),
    record({ time: at(500), attempt: 1, phase: 'review', step_id: 'review-1', event: 'cli_exit', status: 'exited', exit_code: 0 }),
    record({ time: at(400), source: 'receipt', phase: 'review', event: 'phase', status: 'passed', evidence: 's'.repeat(64) }),
  ]);
  assert.equal(current.actors[MANAGER].caption, 'ревью: PASS');
});

test('a triage report registered after a review receipt is published as the newer fact', () => {
  const reviewed = record({ time: at(300), phase: 'review', step_id: 'review-1', source: 'receipt', event: 'phase',
                            status: 'failed', evidence: 't'.repeat(64) });
  const after = project(
    [reviewed],
    [traceRecord({ time: at(60), kind: 'message', message_kind: 'feedback', role: 'manager', phase: 'triage', step_id: 'triage-1' })],
  );
  assert.equal(after.actors[MANAGER].state, 'idle');
  assert.equal(after.actors[MANAGER].caption, 'разбор: обратная связь зарегистрирована');
  assert.match(after.actors[MANAGER].provenance, /состав замечаний неизвестен/);
  assert.notEqual(after.triage, null);

  // Order decides, not the kind of the record: an older report does not replace a newer receipt.
  const before = project(
    [record({ time: at(60), phase: 'review', step_id: 'review-1', source: 'receipt', event: 'phase', status: 'failed',
              evidence: 'u'.repeat(64) })],
    [traceRecord({ time: at(300), kind: 'message', message_kind: 'feedback', role: 'manager', phase: 'triage', step_id: 'triage-1' })],
  );
  assert.equal(before.actors[MANAGER].caption, 'ревью: FAIL');
});

test('records of another run are counted and named, never merged into this one', () => {
  const state = project(
    [record({ run_id: 'run-a', event: 'run', status: 'started' }),
     record({ run_id: 'run-b', event: 'cli_exit', status: 'exited', exit_code: 7 })],
    [traceRecord({ run_id: 'run-b', kind: 'status', state: 'api_retry', attempt_no: 3 })],
  );
  assert.equal(state.runId, 'run-a');
  assert.equal(state.actors[IMPLEMENTER].state, 'idle');
  assert.match(state.actors[IMPLEMENTER].caption, /запуск запрошен/);
  assert.doesNotMatch(state.actors[IMPLEMENTER].caption, /кодом 7/);
  assert.deepEqual(state.foreign, { 'run-b': 2 });
  // The feed itself is readable, so the actors keep their states and the problem is said out loud.
  assert.equal(state.source.available, true);
  assert.match(state.source.note, /run-b/);
  assert.match(state.source.note, /run-a/);
});

test('every actor carries a compact form of its caption for the always-on label', () => {
  const state = project([
    LAUNCH,
    record({ source: 'native', event: 'tool_call', status: 'observed', tool: 'Edit', component: 'src', call_id: 'c1' }),
  ]);
  assert.equal(state.actors[IMPLEMENTER].caption, 'Edit (src)');
  assert.equal(state.actors[IMPLEMENTER].short, 'Edit');
  for (const id of [USER, MANAGER, IMPLEMENTER]) {
    const actor = state.actors[id];
    assert.ok(actor.short, 'actor ' + id + ' has no compact caption');
    assert.ok(actor.short.length <= actor.caption.length, 'the compact caption of ' + id + ' is not shorter');
    assert.ok(actor.short.length <= 24, 'the compact caption of ' + id + ' is too long: ' + actor.short);
  }
  const offline = project([LAUNCH], [], NOW, { available: false, detail: 'events: источник недоступен' });
  assert.equal(offline.actors[IMPLEMENTER].short, 'источник потерян');
});

test('imported history never animates and never becomes a live retry', () => {
  const state = project(
    [LAUNCH, record({ source: 'native', event: 'tool_call', status: 'observed', tool: 'Bash', call_id: 'c1' })],
    [traceRecord({ source: 'import', kind: 'status', state: 'api_retry', attempt_no: 7 }),
     traceRecord({ source: 'import', kind: 'message', message_kind: 'user_prompt', role: 'user' })],
  );
  assert.equal(state.actors[IMPLEMENTER].state, 'working');
  assert.equal(state.actors[USER].caption, 'запроса в трассировке нет');
});

test('an unavailable source suppresses every activity claim', () => {
  const state = project(
    [LAUNCH, record({ source: 'native', event: 'tool_call', status: 'observed', tool: 'Bash', call_id: 'c1' })],
    [],
    NOW,
    { available: false, detail: 'events: источник недоступен' },
  );
  for (const id of [MANAGER, IMPLEMENTER]) {
    assert.equal(state.actors[id].state, 'offline');
    assert.equal(state.actors[id].caption, 'источник недоступен, состояние не подтверждено');
    assert.equal(state.actors[id].toolName, undefined);
  }
  assert.equal(state.source.available, false);
  assert.equal(state.actors[USER].state, 'human');
});

test('a live session outranks an older recorded result', () => {
  const state = project([
    record({ time: at(300), source: 'receipt', phase: 'review', event: 'phase', status: 'failed', evidence: 'j'.repeat(64) }),
    record({ time: at(20), phase: 'review', step_id: 'review-2', event: 'run', status: 'started' }),
    record({ time: at(10), phase: 'review', step_id: 'review-2', source: 'native', event: 'tool_call', status: 'observed', tool: 'Read', call_id: 'r2' }),
  ]);
  assert.equal(state.actors[MANAGER].state, 'working');
  assert.equal(state.actors[MANAGER].caption, 'Read');
});

test('two live invocations of one role are counted, not hidden', () => {
  const state = project([
    record({ step_id: 'build-1', event: 'run', status: 'started' }),
    record({ step_id: 'build-2', event: 'run', status: 'started' }),
    record({ step_id: 'build-2', source: 'native', event: 'tool_call', status: 'observed', tool: 'Edit', call_id: 'c2' }),
  ]);
  assert.match(state.actors[IMPLEMENTER].provenance, /2 параллельных сессии/);
});

test('the same records applied twice produce the same state', () => {
  const records = [LAUNCH, record({ source: 'native', event: 'tool_call', status: 'observed', tool: 'Bash', call_id: 'c1' })];
  const once = foldJournal(records, emptyJournalFold());
  const twice = foldJournal(records, foldJournal(records, emptyJournalFold()));
  assert.equal(twice.steps.size, once.steps.size);
  assert.deepEqual(
    projectOffice({ journal: twice, trace: emptyTraceFold(), now: NOW }).actors,
    projectOffice({ journal: once, trace: emptyTraceFold(), now: NOW }).actors,
  );
});

test('a full repair cycle keeps every stage distinct', () => {
  const snapshotOne = 'k'.repeat(64);
  const snapshotTwo = 'l'.repeat(64);
  const cycle = [
    record({ attempt: 1, event: 'run', status: 'started' }),
    record({ attempt: 1, event: 'cli_exit', status: 'exited', exit_code: 0 }),
    record({ attempt: 1, event: 'result', status: 'ready' }),
    record({ attempt: 1, source: 'receipt', phase: 'tests', event: 'phase', status: 'failed', evidence: 'm'.repeat(64), snapshot: snapshotOne, component: 'python', count: 1 }),
    record({ attempt: 1, source: 'manager', phase: 'decision', step_id: 'decision', event: 'decision', status: 'retry' }),
    record({ attempt: 2, step_id: 'build-2', event: 'run', status: 'started' }),
    record({ attempt: 2, step_id: 'build-2', event: 'cli_exit', status: 'exited', exit_code: 0 }),
    record({ attempt: 2, step_id: 'build-2', event: 'result', status: 'ready' }),
    record({ attempt: 2, source: 'receipt', phase: 'tests', event: 'phase', status: 'passed', evidence: 'n'.repeat(64), snapshot: snapshotTwo, component: 'python', count: 1 }),
    record({ attempt: 2, source: 'receipt', phase: 'review', event: 'phase', status: 'passed', evidence: 'o'.repeat(64), snapshot: snapshotTwo }),
    record({ attempt: 2, source: 'manager', phase: 'decision', step_id: 'decision', event: 'decision', status: 'complete', evidence: 'p'.repeat(64) }),
  ];
  const captions = [];
  const fold = emptyJournalFold();
  for (const item of cycle) {
    foldJournal([item], fold);
    captions.push(projectOffice({ journal: fold, trace: emptyTraceFold(), now: NOW }).actors[MANAGER].caption);
  }
  assert.deepEqual(captions.slice(3), [
    'проверки: 0 PASS, 1 FAIL, из 1',
    'решение менеджера: RETRY',
    'решение менеджера: RETRY',
    'решение менеджера: RETRY',
    'решение менеджера: RETRY',
    'проверки: 1 PASS, из 1',
    'ревью: PASS',
    'решение менеджера: COMPLETE',
  ]);
  assert.equal(projectOffice({ journal: fold, trace: emptyTraceFold(), now: NOW }).attempt, 2);
});
