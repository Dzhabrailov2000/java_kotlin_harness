"""Verify component selection against realistic event and hook inputs."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "harness_run_audit.py"
SPEC = importlib.util.spec_from_file_location("harness_run_audit", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def tool_call(identifier, name, tool_input=None, parent=None):
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"content": [{"type": "tool_use", "id": identifier,
                                     "name": name, "input": tool_input or {}}]}}


def tool_result(identifier, *, is_error=False, parent=None):
    return {"type": "user", "parent_tool_use_id": parent,
            "message": {"content": [{"type": "tool_result", "tool_use_id": identifier,
                                     "is_error": is_error, "content": "PRIVATE_RESULT"}]}}


def task_started(task_id, tool_use_id=None, task_type="local_agent"):
    event = {"type": "system", "subtype": "task_started", "task_id": task_id,
             "description": "PRIVATE_DESCRIPTION", "task_type": task_type,
             "uuid": "uuid-started-" + task_id, "session_id": "session-1"}
    if tool_use_id is not None:
        event["tool_use_id"] = tool_use_id
    return event


def task_notification(task_id, status, tool_use_id=None):
    event = {"type": "system", "subtype": "task_notification", "task_id": task_id,
             "status": status, "output_file": "PRIVATE_OUTPUT_FILE", "summary": "PRIVATE_SUMMARY",
             "uuid": "uuid-notified-" + task_id, "session_id": "session-1"}
    if tool_use_id is not None:
        event["tool_use_id"] = tool_use_id
    return event


class HarnessRunAuditTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="harness-audit-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.selection = {"skills": ["scope-fence"], "agents": ["code-explorer"],
                          "mcp_servers": ["context7"]}

    def audit(self, events, selection=None, raw_lines=()):
        path = self.directory / "events.jsonl"
        path.write_text("\n".join([*(json.dumps(event) for event in events), *raw_lines]), encoding="utf-8")
        return AUDIT.audit_run(path, self.selection if selection is None else selection)

    def test_duplicate_calls_and_results_include_child_activity_without_private_content(self):
        agent = tool_call("agent-1", "Agent", {"subagent_type": "code-explorer", "prompt": "PRIVATE_PROMPT"})
        events = [
            {"type": "system", "subtype": "init", "skills": ["scope-fence", "unselected"],
             "agents": ["code-explorer", "judge"], "tools": ["Agent", "Read"],
             "mcp_servers": [{"name": "context7", "status": "connected", "env": "PRIVATE_ENV"}]},
            {"type": "stream_event", "event": {"type": "content_block_start", "index": 0,
             "content_block": {"type": "tool_use", "id": "agent-1", "name": "Agent", "input": {}}}},
            agent, agent,
            tool_call("read-1", "Read", {"file_path": "PRIVATE_PATH"}, parent="agent-1"),
            tool_result("read-1", parent="agent-1"), tool_result("agent-1"), tool_result("agent-1"),
            tool_call("skill-1", "Skill", {"skill": "scope-fence PRIVATE_ARGS"}), tool_result("skill-1"),
        ]
        result = self.audit(events)
        self.assertEqual(result["status"], "RECORDED", result)
        self.assertEqual(len(result["calls"]), 3)
        self.assertTrue(all(call["result_status"] == "TOOL_RETURNED" for call in result["calls"]))
        self.assertEqual(result["calls"][1]["parent_tool_use_id"], "agent-1")
        self.assertEqual(result["mcp_servers"], {"called": [], "unused": ["context7"]})
        self.assertIn("unselected", result["init_catalog"][0]["skills"])
        self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_catalog_presence_is_not_a_required_agent_call(self):
        result = self.audit([{"type": "system", "subtype": "init", "agents": ["code-explorer"]}])
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["missing_agents"], ["code-explorer"])

    def test_agent_error_and_missing_result_cannot_satisfy_required_agent(self):
        for returned in (False, True):
            with self.subTest(returned=returned):
                events = [tool_call("a", "Task", {"subagent_type": "code-explorer"})]
                if returned:
                    events.append(tool_result("a", is_error=True))
                result = self.audit(events)
                self.assertEqual(result["status"], "UNVERIFIED")
                self.assertEqual(result["missing_agents"], ["code-explorer"])
                self.assertEqual(result["calls"][0]["result_status"], "ERROR" if returned else "NO_RESULT")

    def test_task_alias_and_mcp_call_are_recorded(self):
        result = self.audit([
            tool_call("a", "Task", {"subagent_type": "code-explorer"}), tool_result("a"),
            tool_call("m", "mcp__context7__query_docs", {"query": "PRIVATE_QUERY"}), tool_result("m"),
        ])
        self.assertEqual(result["status"], "RECORDED")
        self.assertEqual(result["mcp_servers"], {"called": ["context7"], "unused": []})

    def test_unexpected_components_include_nested_calls(self):
        result = self.audit([
            tool_call("a", "Agent", {"subagent_type": "code-explorer"}), tool_result("a"),
            tool_call("other-agent", "Task", {"subagent_type": "judge"}, parent="a"),
            tool_call("other-skill", "Skill", {"skill": "api-design private arguments"}),
            tool_call("other-mcp", "mcp__idea__execute_code", {"code": "PRIVATE_CODE"}),
        ])
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual({call["component"] for call in result["unexpected_calls"]},
                         {"judge", "api-design", "idea"})

    def test_parse_errors_empty_stream_and_conflicting_duplicates_are_unverified(self):
        cases = [([], ()), ([[]], ()), ([{"type": "assistant", "message": None}], ()),
                 ([{"type": "system", "subtype": "init"}], ("PRIVATE_INVALID_JSON",)),
                 ([tool_result("missing")], ()),
                 ([tool_call("a", "Read"), tool_call("a", "Write")], ()),
                 ([tool_call("a", "Read"), tool_result("a"), tool_result("a", is_error=True)], ())]
        for events, raw_lines in cases:
            with self.subTest(events=events, raw_lines=raw_lines):
                result = self.audit(events, raw_lines=raw_lines)
                self.assertEqual(result["status"], "UNVERIFIED")
                self.assertTrue(result["parse_errors"])
                self.assertNotIn("PRIVATE_", json.dumps(result))

    def background_agent(self, status, *, flag=True, notification_link="agent-1"):
        tool_input = {"subagent_type": "code-explorer", "prompt": "PRIVATE_PROMPT"}
        if flag:
            tool_input["run_in_background"] = True
        events = [tool_call("agent-1", "Agent", tool_input), task_started("task-1", "agent-1"),
                  tool_result("agent-1")]
        if status is not None:
            events.append(task_notification("task-1", status, notification_link))
        return events

    def test_background_launch_ack_failed_and_stopped_tasks_do_not_satisfy_required_agent(self):
        for status, expected in ((None, "STARTED"), ("failed", "FAILED"), ("stopped", "STOPPED")):
            with self.subTest(status=status):
                result = self.audit(self.background_agent(status))
                self.assertEqual(result["status"], "UNVERIFIED", result)
                self.assertEqual(result["missing_agents"], ["code-explorer"])
                self.assertEqual(result["parse_errors"], [])
                call = result["calls"][0]
                self.assertEqual(call["result_status"], "TOOL_RETURNED")
                self.assertEqual(call.get("task_status"), expected)
                self.assertEqual(call.get("task_id"), "task-1")
                self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_completed_task_satisfies_required_agent_only_when_linked_without_errors(self):
        for label, events in (
            ("linked by tool_use_id", self.background_agent("completed")),
            ("linked by task_id only", self.background_agent("completed", notification_link=None)),
            ("linked by notification only", [
                tool_call("agent-1", "Agent", {"subagent_type": "code-explorer"}),
                tool_result("agent-1"), task_notification("task-1", "completed", "agent-1")]),
        ):
            with self.subTest(case=label):
                result = self.audit(events)
                self.assertEqual(result["status"], "RECORDED", result)
                self.assertEqual(result["missing_agents"], [])
                self.assertEqual(result["calls"][0].get("task_status"), "COMPLETED")
                self.assertNotIn("PRIVATE_", json.dumps(result))
        errored = [tool_call("agent-1", "Agent", {"subagent_type": "code-explorer"}),
                   task_started("task-1", "agent-1"), tool_result("agent-1", is_error=True),
                   task_notification("task-1", "completed", "agent-1")]
        result = self.audit(errored)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["missing_agents"], ["code-explorer"])
        self.assertEqual(result["calls"][0]["result_status"], "ERROR")
        self.assertEqual(result["calls"][0].get("task_status"), "COMPLETED")

    def test_native_task_lifecycle_counts_without_run_in_background_flag(self):
        failed = self.audit(self.background_agent("failed", flag=False))
        self.assertEqual(failed["status"], "UNVERIFIED", failed)
        self.assertEqual(failed["missing_agents"], ["code-explorer"])
        self.assertEqual(failed["calls"][0]["task_status"], "FAILED")
        completed = self.audit(self.background_agent("completed", flag=False))
        self.assertEqual(completed["status"], "RECORDED", completed)
        self.assertEqual(completed["calls"][0]["task_status"], "COMPLETED")
        # Without a native task lifecycle a foreground tool result is the actual result.
        for tool_input in ({"subagent_type": "code-explorer"},
                           {"subagent_type": "code-explorer", "run_in_background": False}):
            with self.subTest(tool_input=tool_input):
                result = self.audit([tool_call("agent-1", "Agent", tool_input), tool_result("agent-1")])
                self.assertEqual(result["status"], "RECORDED", result)
                self.assertEqual(result["missing_agents"], [])
                self.assertFalse(result["calls"][0]["background_requested"])
                self.assertIsNone(result["calls"][0]["task_status"])
                self.assertIsNone(result["calls"][0]["task_id"])

    def test_requested_background_run_without_task_lifecycle_does_not_satisfy_required_agent(self):
        requested = {"subagent_type": "code-explorer", "run_in_background": True, "prompt": "PRIVATE_PROMPT"}
        provisional = {"type": "stream_event", "event": {"type": "content_block_start", "index": 0,
                       "content_block": {"type": "tool_use", "id": "agent-1", "name": "Agent", "input": {}}}}
        bash = tool_call("bash-1", "Bash", {"command": "PRIVATE_COMMAND", "run_in_background": True})
        for label, events in (
            ("acknowledged only", [tool_call("agent-1", "Agent", requested), tool_result("agent-1")]),
            ("acknowledged after provisional stream block",
             [provisional, tool_call("agent-1", "Agent", requested), tool_result("agent-1")]),
            ("another call's task completed",
             [tool_call("agent-1", "Agent", requested), tool_result("agent-1"), bash,
              task_started("task-b", "bash-1", task_type="local_bash"), tool_result("bash-1"),
              task_notification("task-b", "completed", "bash-1")]),
        ):
            with self.subTest(case=label):
                result = self.audit(events)
                self.assertEqual(result["status"], "UNVERIFIED", result)
                self.assertEqual(result["missing_agents"], ["code-explorer"])
                self.assertEqual(result["parse_errors"], [])
                call = result["calls"][0]
                self.assertEqual(call["result_status"], "TOOL_RETURNED")
                self.assertTrue(call["background_requested"])
                self.assertIsNone(call["task_status"])
                self.assertIsNone(call["task_id"])
                self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_task_events_are_linked_by_identifiers_not_by_agent_name_or_order(self):
        agent = tool_call("agent-1", "Agent", {"subagent_type": "code-explorer", "prompt": "PRIVATE_PROMPT"})
        bash = tool_call("bash-1", "Bash", {"command": "PRIVATE_COMMAND", "run_in_background": True})
        bash_task = [task_started("task-b", "bash-1", task_type="local_bash"), tool_result("bash-1")]
        result = self.audit([agent, tool_result("agent-1"), bash, *bash_task,
                             task_notification("task-b", "failed", "bash-1")])
        self.assertEqual(result["status"], "RECORDED", result)
        self.assertEqual(result["missing_agents"], [])
        statuses = {call["id"]: call.get("task_status") for call in result["calls"]}
        self.assertEqual(statuses, {"agent-1": None, "bash-1": "FAILED"})
        result = self.audit([agent, task_started("task-1", "agent-1"), tool_result("agent-1"), bash, *bash_task,
                             task_notification("task-b", "completed", "bash-1")])
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertEqual(result["missing_agents"], ["code-explorer"])
        statuses = {call["id"]: call["task_status"] for call in result["calls"]}
        self.assertEqual(statuses, {"agent-1": "STARTED", "bash-1": "COMPLETED"})
        for label, events in (
            ("no link at all", [task_started("task-x"), task_notification("task-x", "completed")]),
            ("unknown tool_use_id", [task_notification("task-y", "completed", "ghost")]),
        ):
            with self.subTest(case=label):
                result = self.audit([agent, tool_result("agent-1"), *events])
                self.assertEqual(result["status"], "UNVERIFIED", result)
                self.assertIn("unmatched_task", {error["reason"] for error in result["parse_errors"]})
                self.assertIsNone(result["calls"][0]["task_status"])
                self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_repeated_consistent_task_events_pass_and_contradictions_are_unverified(self):
        call, started, ack, completed = self.background_agent("completed")
        result = self.audit([call, started, started, ack, ack, completed, completed])
        self.assertEqual(result["status"], "RECORDED", result)
        self.assertEqual(result["parse_errors"], [])
        self.assertEqual(result["calls"][0].get("task_status"), "COMPLETED")
        contradicted = self.audit([call, started, ack, completed, task_notification("task-1", "failed", "agent-1")])
        self.assertEqual(contradicted["status"], "UNVERIFIED")
        self.assertEqual(contradicted["missing_agents"], ["code-explorer"])
        self.assertEqual(contradicted["calls"][0]["task_status"], "FAILED")
        self.assertIn("conflicting_task_notification", {error["reason"] for error in contradicted["parse_errors"]})
        for reason, extra in (
            ("conflicting_task_link", [task_notification("task-1", "completed", "other-call")]),
            ("conflicting_task_link", [task_started("task-2", "agent-1"), task_notification("task-2", "completed")]),
            ("invalid_task_notification", [task_notification("task-1", "PRIVATE_UNKNOWN", "agent-1")]),
            ("invalid_task_event", [{"type": "system", "subtype": "task_started", "task_id": 7}]),
        ):
            with self.subTest(reason=reason, extra=extra):
                result = self.audit([call, started, ack, *extra])
                self.assertEqual(result["status"], "UNVERIFIED", result)
                self.assertIn(reason, {error["reason"] for error in result["parse_errors"]})
                self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_required_agent_failure_or_pending_call_is_not_masked_by_another_completed_call(self):
        explorer = {"subagent_type": "code-explorer"}
        for label, events in (
            ("errored foreground call", [tool_call("a", "Agent", explorer), tool_result("a", is_error=True),
                                         tool_call("b", "Agent", explorer), tool_result("b")]),
            ("call without result", [tool_call("a", "Agent", explorer),
                                     tool_call("b", "Agent", explorer), tool_result("b")]),
            ("background request without task events",
             [tool_call("a", "Agent", {**explorer, "run_in_background": True}), tool_result("a"),
              tool_call("b", "Agent", explorer), tool_result("b")]),
            ("failed background call", [tool_call("a", "Agent", explorer), task_started("task-a", "a"),
                                        tool_result("a"), task_notification("task-a", "failed", "a"),
                                        tool_call("b", "Agent", explorer), tool_result("b")]),
            ("pending background call", [tool_call("a", "Agent", explorer), task_started("task-a", "a"),
                                         tool_result("a"), tool_call("b", "Agent", explorer),
                                         task_started("task-b", "b"), tool_result("b"),
                                         task_notification("task-b", "completed", "b")]),
        ):
            with self.subTest(case=label):
                result = self.audit(events)
                self.assertEqual(result["status"], "UNVERIFIED", result)
                self.assertEqual(result["missing_agents"], ["code-explorer"])
                self.assertEqual(result["parse_errors"], [])

    def test_hook_lifecycle_metadata_is_preserved_without_command_output(self):
        events = [{"type": "system", "subtype": subtype, "hook_id": "hook-1",
                   "hook_name": "selection-guard", "hook_event": "PreToolUse",
                   "outcome": "success", "exit_code": 0,
                   "stdout": "PRIVATE_STDOUT", "stderr": "PRIVATE_STDERR",
                   "output": "PRIVATE_OUTPUT", "command": "PRIVATE_COMMAND"}
                  for subtype in ("hook_started", "hook_progress", "hook_response")]
        result = self.audit(events, selection={"skills": [], "agents": [], "mcp_servers": []})
        self.assertEqual(result["status"], "RECORDED")
        self.assertEqual([event["subtype"] for event in result["hook_events"]],
                         [event["subtype"] for event in events])
        self.assertTrue(all(event["exit_code"] == 0 for event in result["hook_events"]))
        self.assertNotIn("PRIVATE_", json.dumps(result))

    def hook(self, payload, selection=None, *, raw_payload=None, raw_selection=None):
        path = self.directory / "selection.json"
        path.write_text(json.dumps(self.selection if selection is None else selection)
                        if raw_selection is None else raw_selection, encoding="utf-8")
        process = subprocess.run([sys.executable, str(SCRIPT), "--selection", str(path)],
                                 input=json.dumps(payload) if raw_payload is None else raw_payload,
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        return json.loads(process.stdout)["hookSpecificOutput"]

    def test_hook_permits_selected_components_and_unmatched_builtins(self):
        for name, tool_input in (
            ("Skill", {"skill": " scope-fence some arguments "}),
            ("Agent", {"subagent_type": "code-explorer"}),
            ("Task", {"subagent_type": "code-explorer"}),
            ("mcp__context7__query_docs", {"query": "private arguments"}),
            ("Read", {"file_path": "private path"}),
        ):
            with self.subTest(name=name):
                result = self.hook({"tool_name": name, "tool_input": tool_input})
                self.assertEqual(result["permissionDecision"], "allow")
                self.assertEqual(result["hookEventName"], "PreToolUse")

    def test_hook_denies_unselected_and_malformed_components(self):
        for payload in (
            {"tool_name": "Skill", "tool_input": {"skill": "scope-fence-other"}},
            {"tool_name": "Agent", "tool_input": {"subagent_type": "judge"}},
            {"tool_name": "Task", "tool_input": {"subagent_type": "judge"}},
            {"tool_name": "mcp__idea__read_file", "tool_input": {}},
            {"tool_name": "mcp__context7", "tool_input": {}},
            {"tool_name": "Skill", "tool_input": {}},
            {"tool_name": "Agent", "tool_input": {"subagent_type": []}},
            {"tool_name": "Read", "tool_input": "PRIVATE_INVALID"},
            {"tool_name": "Read"}, [], None,
        ):
            with self.subTest(payload=payload):
                result = self.hook(payload)
                self.assertEqual(result["permissionDecision"], "deny")
                self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_hook_invalid_json_or_selection_fails_closed(self):
        for options in (
            {"raw_payload": "PRIVATE_INVALID_JSON"},
            {"raw_selection": "PRIVATE_INVALID_JSON"},
            {"selection": {}},
            {"selection": {"skills": "scope-fence", "agents": [], "mcp_servers": []}},
            {"selection": {"skills": [], "agents": [None], "mcp_servers": []}},
        ):
            with self.subTest(options=options):
                result = self.hook({"tool_name": "Read", "tool_input": {}}, **options)
                self.assertEqual(result["permissionDecision"], "deny")
                self.assertNotIn("PRIVATE_", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
