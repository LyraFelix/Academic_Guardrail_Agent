"""Run one isolated, text-only Codex judgment; retain every attempt and token count.

This optional evaluation adapter uses the user's installed/logged-in CLI. It is
not imported by the MCP server and never reads authentication files.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

MODEL = "gpt-6.1-sol"
REASONING = "high"
DISABLED_FEATURES = ("shell_tool", "unified_exec", "apps", "plugins", "multi_agent",
                     "memories", "hooks", "browser_use", "computer_use", "image_generation",
                     "view_image", "code_mode_host", "sleep_tool", "shell_snapshot",
                     "remote_plugin", "unbounded_connection_retries")


def strict_schema(schema):
    """The CLI's structured output requires every object key; defaults become explicit."""
    if isinstance(schema, list):
        return [strict_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: strict_schema(value) for key, value in schema.items() if key != "default"}
    if result.get("type") == "object":
        result["required"] = list(result.get("properties", {}))
        result["additionalProperties"] = False
    return result


def command_for(executable, schema_path, response_path):
    command = [executable, "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
               "--sandbox", "read-only", "--json", "--color", "never", "--model", MODEL,
               "--output-schema", str(schema_path), "-o", str(response_path)]
    for feature in DISABLED_FEATURES:
        command += ["--disable", feature]
    command += ["--enable", "skip_host_skill_discovery", "--enable", "omit_skill_descriptions"]
    for value in (f'model_reasoning_effort="{REASONING}"', 'web_search="disabled"',
                  'project_doc_max_bytes=0', 'skills.max_context_tokens=1',
                  'memories.use_memories=false', 'memories.generate_memories=false'):
        command += ["-c", value]
    return command + ["-"]


def parse_events(text):
    """Startup warnings are not failed judgments; tool use or failed turns are."""
    events = [json.loads(line) for line in text.splitlines() if line.strip()]
    turns = [event for event in events if event.get("type") == "turn.completed"]
    items = [event["item"] for event in events
             if event.get("type") in {"item.started", "item.updated", "item.completed"}]
    tool_items = sorted({item.get("type", "unknown") for item in items
                         if item.get("type") not in {"agent_message", "reasoning", "error"}})
    return {"thread_ids": [event["thread_id"] for event in events if event.get("type") == "thread.started"],
            "completed_turns": len(turns), "usage": turns[-1].get("usage") if len(turns) == 1 else None,
            "tool_items": tool_items,
            "failed_turns": sum(event.get("type") in {"turn.failed", "error"} for event in events),
            "warnings": [item.get("message", "") for item in items if item.get("type") == "error"]}


def invoke(prompt, schema, destination, timeout=120):
    """One attempt, no harness retries. A new output directory prevents overwrites."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    executable = shutil.which("codex")
    if executable is None:
        raise RuntimeError("Install and log in to Codex CLI before running this optional comparison")
    (destination / "prompt.txt").write_bytes(prompt.encode("utf-8"))
    schema_path, response_path = destination / "schema.json", destination / "response.json"
    schema_path.write_text(json.dumps(strict_schema(schema), ensure_ascii=False), encoding="utf-8")
    command = command_for(executable, schema_path, response_path)
    (destination / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    env = dict(os.environ)
    for key in ("CODEX_THREAD_ID", "CODEX_PARENT_THREAD_ID"):
        env.pop(key, None)
    started = time.monotonic()
    error, returncode = None, None
    with tempfile.TemporaryDirectory(prefix="guardrail_text_judge_") as cwd:
        try:
            process = subprocess.run(command, input=prompt.encode("utf-8"),
                                     capture_output=True, cwd=cwd, env=env, timeout=timeout)
            stdout, stderr = process.stdout.decode("utf-8", "replace"), process.stderr.decode("utf-8", "replace")
            returncode = process.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, error = exc.stdout or "", exc.stderr or "", "timeout"
            stdout = stdout.decode("utf-8", "replace") if isinstance(stdout, bytes) else stdout
            stderr = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    (destination / "events.jsonl").write_text(stdout, encoding="utf-8")
    (destination / "stderr.txt").write_text(stderr, encoding="utf-8")
    event_stream_valid = True
    try:
        events = parse_events(stdout)
    except (ValueError, KeyError, TypeError):
        event_stream_valid = False
        error = error or "invalid_event_stream"
        events = {"thread_ids": [], "completed_turns": 0, "usage": None, "tool_items": [], "failed_turns": 0, "warnings": []}
    response = None
    if error is None:
        if returncode != 0 or events["completed_turns"] != 1 or len(events["thread_ids"]) != 1 or events["failed_turns"]:
            error = "cli_or_turn_failure"
        elif events["tool_items"]:
            error = "unexpected_tool_use"
        else:
            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                error = "missing_or_invalid_json"
    result = {"requested_model": MODEL, "reasoning": REASONING, "elapsed_seconds": time.monotonic() - started,
              "returncode": returncode, "error": error, "event_stream_valid": event_stream_valid,
              "response": response, **events}
    (destination / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
