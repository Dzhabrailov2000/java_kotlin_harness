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
