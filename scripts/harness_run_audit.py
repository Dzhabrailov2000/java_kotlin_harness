#!/usr/bin/env python3
"""Record component calls and enforce the manager's explicit selection."""

import argparse
import json
from pathlib import Path
import re
import sys


NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*\Z")
SELECTION_KEYS = ("skills", "agents", "mcp_servers")


def validate_selection(selection):
    if not isinstance(selection, dict):
        raise ValueError("Selection must be an object")
    selected = {}
    for key in SELECTION_KEYS:
        values = selection.get(key)
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not NAME.fullmatch(value)
            or (key == "mcp_servers" and "__" in value)
            for value in values
        ):
            raise ValueError("Selection requires valid component name lists")
        selected[key] = list(dict.fromkeys(values))
    return selected


def component_for(name, tool_input):
    """Extract identifiers only; arguments and returned content stay private."""
    if name == "Skill":
        value = tool_input.get("skill")
        component = value.strip().split()[0] if isinstance(value, str) and value.strip() else None
        return "skills", component if component and NAME.fullmatch(component) else None
    if name in ("Agent", "Task"):
        value = tool_input.get("subagent_type")
        return "agents", value if isinstance(value, str) and NAME.fullmatch(value) else None
    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        component = parts[1] if len(parts) == 3 and parts[2] else None
        return "mcp_servers", component if component and NAME.fullmatch(component) else None
    return "builtin", None


def hook_decision(payload, selection):
    try:
        selected = validate_selection(selection)
        if not isinstance(payload, dict):
            raise ValueError("Hook payload must be an object")
        name, tool_input = payload.get("tool_name"), payload.get("tool_input")
        if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(tool_input, dict):
            raise ValueError("Hook payload requires a tool name and input object")
        kind, component = component_for(name, tool_input)
        allowed = kind == "builtin" or component in selected[kind]
        reason = "Component is permitted by the manager's selection" if allowed else "Component is absent from the manager's selection"
    except ValueError:
        allowed, reason = False, "Invalid hook payload or selection; component use is denied"
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow" if allowed else "deny",
        "permissionDecisionReason": reason,
    }}


def audit_run(events_path, selection):
    """Audit observable delivery and calls, without judging implementation quality."""
    errors, catalogs, hooks, calls, results = [], [], [], {}, {}
    try:
        selected = validate_selection(selection)
    except ValueError:
        selected = {key: [] for key in SELECTION_KEYS}
        errors.append({"reason": "invalid_selection"})

    def error(line, reason):
        errors.append({"line": line, "reason": reason})

    def block_seen(block, parent, line, provisional=False):
        if not isinstance(block, dict):
            error(line, "invalid_content_block")
            return
        if block.get("type") == "tool_use":
            identifier, name, tool_input = block.get("id"), block.get("name"), block.get("input", {})
            if (not isinstance(identifier, str) or not identifier or not isinstance(name, str)
                    or not NAME.fullmatch(name) or not isinstance(tool_input, dict)):
                error(line, "invalid_tool_use")
                return
            kind, component = component_for(name, tool_input)
            call = {"id": identifier, "name": name, "kind": kind, "component": component,
                    "parent_tool_use_id": parent, "result_status": "NO_RESULT"}
            previous = calls.get(identifier)
            if previous:
                if (previous["name"] != name or previous["parent_tool_use_id"] != parent
                        or (previous["component"] and component and previous["component"] != component)):
                    error(line, "conflicting_tool_use_id")
                    return
                if component is not None:
                    previous["component"] = component
            else:
                calls[identifier] = call
            if kind != "builtin" and component is None and not provisional:
                error(line, "missing_component_identifier")
        elif block.get("type") == "tool_result":
            identifier, is_error = block.get("tool_use_id"), block.get("is_error", False)
            if not isinstance(identifier, str) or not identifier or not isinstance(is_error, bool):
                error(line, "invalid_tool_result")
                return
            status = "ERROR" if is_error else "TOOL_RETURNED"
            previous = results.get(identifier)
            if previous and previous != status:
                error(line, "conflicting_tool_result")
            results[identifier] = "ERROR" if "ERROR" in (previous, status) else status

    try:
        lines = Path(events_path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        lines = []
        errors.append({"reason": "unreadable_events"})
    event_count = 0
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            error(line_number, "invalid_json")
            continue
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            error(line_number, "invalid_event")
            continue
        event_count += 1
        parent = event.get("parent_tool_use_id")
        if parent is not None and not isinstance(parent, str):
            error(line_number, "invalid_parent_tool_use_id")
            parent = None
        if event["type"] == "system" and event.get("subtype") == "init":
            catalog = {"parent_tool_use_id": parent}
            for key in ("tools", "skills", "agents", "mcp_servers"):
                values = event.get(key, [])
                if not isinstance(values, list):
                    error(line_number, "invalid_init_catalog")
                    values = []
                catalog[key] = []
                for value in values:
                    name = value.get("name") if isinstance(value, dict) else value
                    if isinstance(name, str) and NAME.fullmatch(name):
                        catalog[key].append(name)
            catalogs.append(catalog)
        subtype = event.get("subtype", "")
        if event["type"] == "system" and isinstance(subtype, str) and "hook" in subtype:
            # Lifecycle metadata is preserved; command/stdout/stderr/output are excluded.
            hooks.append({key: event[key] for key in (
                "subtype", "hook_id", "hook_name", "hook_event", "exit_code", "outcome",
                "session_id", "uuid", "parent_tool_use_id",
            ) if key in event and isinstance(event[key], (str, int, float, bool, type(None)))})
        if event["type"] in ("assistant", "user"):
            message = event.get("message", {})
            if not isinstance(message, dict):
                error(line_number, "invalid_message")
                continue
            content = message.get("content", [])
            if isinstance(content, str):
                continue
            if not isinstance(content, list):
                error(line_number, "invalid_message_content")
                continue
            for block in content:
                block_seen(block, parent, line_number)
        elif event["type"] in ("tool_use", "tool_result"):
            block_seen(event, parent, line_number)
        elif event["type"] == "stream_event":
            stream = event.get("event")
            if not isinstance(stream, dict):
                error(line_number, "invalid_stream_event")
            elif stream.get("type") == "content_block_start":
                block_seen(stream.get("content_block"), parent, line_number, provisional=True)

    if not event_count:
        errors.append({"reason": "no_events"})
    for identifier, status in results.items():
        if identifier in calls:
            calls[identifier]["result_status"] = status
        else:
            errors.append({"reason": "unmatched_tool_result", "tool_use_id": identifier})
    observed = list(calls.values())
    unexpected = [call for call in observed
                  if call["kind"] != "builtin" and call["component"] not in selected[call["kind"]]]
    returned_agents = {call["component"] for call in observed
                       if call["kind"] == "agents" and call["result_status"] == "TOOL_RETURNED"}
    missing_agents = [name for name in selected["agents"] if name not in returned_agents]
    called_servers = sorted({call["component"] for call in observed
                             if call["kind"] == "mcp_servers" and call["component"] is not None})
    return {
        "status": "UNVERIFIED" if errors or unexpected or missing_agents else "RECORDED",
        "selected": selected,
        "init_catalog": catalogs,
        "calls": observed,
        "missing_agents": missing_agents,
        "unexpected_calls": unexpected,
        "parse_errors": errors,
        "mcp_servers": {"called": called_servers,
                        "unused": [name for name in selected["mcp_servers"] if name not in called_servers]},
        "hook_events": hooks,
        "meaning": "TOOL_RETURNED records a non-error tool result, not review or acceptance of its contents. "
                   "This audit does not establish code correctness or skill compliance.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()
    try:
        selection = json.loads(args.selection.read_text(encoding="utf-8"))
        payload = json.load(sys.stdin)
        decision = hook_decision(payload, selection)
    except (OSError, UnicodeError, ValueError):
        decision = hook_decision(None, None)
    print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
