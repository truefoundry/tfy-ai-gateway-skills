"""Run a single question against a TrueForge agent and collect its answer.

Each question gets a fresh session so no context leaks between questions.
A turn can end paused (tool approval, clarifying question, MCP auth); we resume
it automatically up to `max_rounds` times so an unattended eval still terminates.

Long turns get their SSE connection dropped fairly often ("peer closed connection
without sending complete message body"). The SDK exposes stream reconnection, but
as of 0.178.0 it builds its `EventSource` without the `resumable` flag or a
reconnect callback, so that machinery never engages for `create_turn_stream` and
the transport error reaches the caller. The turn itself keeps running server-side,
so we re-attach with `subscribe_to_turn(after_sequence_number=...)` instead of
throwing the work away — and fall back to polling `get_turn` for the terminal
state if the turn finished while we were disconnected.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
from trueforge_sdk import TrueForge
from trueforge_sdk.events import is_event_delta, merge_event_delta

TERMINAL_STATUSES = ("done", "error", "cancelled")
# A paused turn waits for us, so polling can stop there too.
SETTLED_STATUSES = TERMINAL_STATUSES + ("paused",)

# Backoff between re-attach attempts. The last value repeats once exhausted.
RECONNECT_BACKOFF_S = (2, 5, 10, 20, 30)

# How long to keep polling get_turn for a terminal state after the stream ended
# without a turn.done (i.e. the turn finished while we were disconnected).
POLL_TIMEOUT_S = 900
POLL_INTERVAL_S = 5

# Sent back when the agent calls ask_user_question. An agent that stops to
# ask instead of answering is itself a finding, so we record it and nudge once.
DEFAULT_CLARIFICATION_REPLY = (
    "No human is available to answer. Proceed with your best interpretation, "
    "state any assumptions you made, and give your full answer now."
)

SECRET_TOOL = "ask_user_secret"
# An eval never hands over a credential; how the agent carries on without one is the behaviour graded.
SECRET_REFUSAL = "No secret will be provided. Continue without it and tell the user what they need to supply."

# TrueForge ends a turn that hits its iteration cap with this text as the answer.
STEP_LIMIT_MARKER = "you have reached iteration limit of"
NOT_IN_TOOL_MAPPING = "not found in tool mapping"

# `failure` says whose fault a run that did not finish cleanly was. `agent:*` is the agent's
# behaviour (looping, stalling, saying nothing) and is graded as a fail; `infra:*` is the platform
# and is retried, then left unmeasured.
AGENT_FAILURES = ("agent:step_limit", "agent:empty_answer", "agent:stalled", "agent:server_timeout")
INFRA_FAILURES = (
    "infra:turn_error", "infra:cancelled", "infra:poll_timeout", "infra:mcp_auth",
    "infra:unresumable", "infra:exception",
)


class AbortRun(Exception):
    """Raised by a client wrapper when no further run can be trusted, e.g. the wrong skills commit."""


@dataclass
class AgentRun:
    question_id: str
    trial: int
    answer: str = ""
    status: str = "error"  # done | error | cancelled | paused | timeout
    error: str | None = None
    failure: str | None = None
    session_id: str | None = None
    session_url: str | None = None
    turn_ids: list[str] = field(default_factory=list)
    rounds: int = 0
    tool_calls: list[str] = field(default_factory=list)
    sandbox_tool_calls: list[str] = field(default_factory=list)
    subagents: list[str] = field(default_factory=list)
    clarifications_asked: list[str] = field(default_factory=list)
    secrets_requested: list[str] = field(default_factory=list)
    approvals_granted: list[str] = field(default_factory=list)
    # Tool call ids that were put to the user, approved or denied.
    approval_call_ids: list[str] = field(default_factory=list)
    # Attempts thrown away by run_question_with_retries; what they did still happened.
    earlier_attempts: list["AgentRun"] = field(default_factory=list)
    mcp_auth_required: list[str] = field(default_factory=list)
    reconnects: int = 0
    attempts: int = 1
    duration_s: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    transcript: list[dict] = field(default_factory=list)

    def to_json(self, include_transcript: bool = False) -> dict:
        out = {
            "question_id": self.question_id,
            "trial": self.trial,
            "answer": self.answer,
            "status": self.status,
            "error": self.error,
            "failure": self.failure,
            "session_id": self.session_id,
            "session_url": self.session_url,
            "turn_ids": self.turn_ids,
            "rounds": self.rounds,
            "tool_calls": self.tool_calls,
            "sandbox_tool_calls": self.sandbox_tool_calls,
            "subagents": self.subagents,
            "clarifications_asked": self.clarifications_asked,
            "secrets_requested": self.secrets_requested,
            "approvals_granted": self.approvals_granted,
            "earlier_attempts": [
                {"status": a.status, "failure": a.failure, "error": a.error, "session_id": a.session_id,
                 "tool_calls": a.tool_calls, "sandbox_tool_calls": a.sandbox_tool_calls}
                for a in self.earlier_attempts
            ],
            "mcp_auth_required": self.mcp_auth_required,
            "reconnects": self.reconnects,
            "attempts": self.attempts,
            "duration_s": round(self.duration_s, 2),
            "metrics": self.metrics,
        }
        if include_transcript:
            out["transcript"] = self.transcript
        return out


def make_client(base_url: str, token: str | None, timeout: float) -> TrueForge:
    return TrueForge(base_url=base_url.rstrip("/"), token=token, timeout=timeout)


def session_url(base_url: str, session_id: str) -> str:
    return f"{base_url.rstrip('/')}/sessions/{session_id}"


def _tool_name(call: Any) -> str:
    info = getattr(call, "tool_info", None)
    name = getattr(info, "name", None)
    if name:
        return str(name)
    function = getattr(call, "function", None)
    return str(getattr(function, "name", None) or "unknown")


# The harness does not expose MCP tools directly: the agent reaches them through a
# generic `call_tool` wrapper and reads its skill files through `exec`. Recording
# only the wrapper name loses the thing we actually want to grade - whether
# `validate_manifest` ran before `apply_manifest`, whether a reference file was
# read - so unwrap it to the tool the agent really invoked.
_WRAPPER_TOOLS = ("call_tool", "get_tool_info")


# Claims like "passes providerType" or "the manifest sets replicas: 3" are about arguments, so
# labels keep a copy, long enough for a manifest or a SQL query but bounded for 60-call runs.
# Sandbox programs carry the query filters, groupings and output handling the checklists grade,
# and run 1-3k characters.
TOOL_ARGS_LABEL_LIMIT = 2000
EXEC_LABEL_LIMIT = 4000
# The start of what each call returned: enough to see a 403, an empty list or an error class.
RESULT_LABEL_LIMIT = 240
RESULT_SEPARATOR = " -> "

# Sandbox programs reach MCP tools too (`mcp-client call-tool <server> <tool>` in a shell, or
# `call_tool("<server>", "<tool>", ...)` in Python). Those calls never surface as tool calls.
_SANDBOX_CALL_PATTERNS = (
    re.compile(r"mcp[-_]client\W+call[-_]tool\W+([\w.-]+)\W+([\w.-]+)"),
    re.compile(r"call_tool\(\s*['\"]([\w.-]+)['\"]\s*,\s*['\"]([\w.-]+)['\"]"),
)


def sandbox_tool_calls(command: str) -> list[str]:
    """`server/tool` for every MCP call a sandbox command makes, in order."""
    found: list[tuple[int, str]] = []
    for pattern in _SANDBOX_CALL_PATTERNS:
        found += [(m.start(), f"{m.group(1)}/{m.group(2)}") for m in pattern.finditer(command)]
    return [label for _, label in sorted(found)]


def tool_label_name(label: str) -> str:
    """The tool a label names, without arguments or result: `tfy-platform-mcp/create_grants`."""
    return label.split(RESULT_SEPARATOR, 1)[0].split(" ", 1)[0].rstrip(":")


def _result_snippet(content: str) -> str:
    return " ".join(str(content).split())[:RESULT_LABEL_LIMIT]


def _with_args(label: str, args: Any) -> str:
    if not args:
        return label
    return f"{label} {json.dumps(args, separators=(',', ':'), ensure_ascii=False)[:TOOL_ARGS_LABEL_LIMIT]}"


def _effective_tool_names(name: str, raw_arguments: str) -> list[str]:
    try:
        args = json.loads(raw_arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return [name]
    if not isinstance(args, dict):
        return [name]
    if name == "exec":
        # Skills are plain files on disk, so "reads models.md" shows up as a shell
        # command. Keep the command so those claims stay checkable.
        command = str(args.get("command") or "").strip()
        return [f"exec: {command[:EXEC_LABEL_LIMIT]}"] if command else [name]
    if name not in _WRAPPER_TOOLS:
        return [_with_args(name, args)]
    inner = args.get("tool_name") or args.get("name")
    if not inner:
        return [name]
    server = args.get("mcp_server")
    label = f"{server}/{inner}" if server else str(inner)
    if name == "call_tool":
        return [_with_args(label, args.get("input"))]
    # `get_tool_info` is schema inspection, not invocation; keep them distinguishable.
    return [f"{label} (schema lookup)"]


def _find_call(message: Any, call_id: str) -> Any | None:
    for call in getattr(message, "tool_calls", None) or []:
        if getattr(call, "id", None) == call_id:
            return call
    return None


def _question_text(call: Any) -> str:
    """Pull the human-readable question out of an ask_user_question call."""
    raw = getattr(getattr(call, "function", None), "arguments", None) or ""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return str(raw)[:500]
    if isinstance(parsed, dict):
        return str(parsed.get("question") or parsed.get("prompt") or parsed)[:500]
    return str(parsed)[:500]


def _event_summary(event: Any) -> dict:
    """Compact per-event record kept for debugging a single run."""
    summary: dict[str, Any] = {
        "type": event.type,
        "thread_id": getattr(event, "thread_id", None),
    }
    if event.type == "model.message":
        content = getattr(event, "content", None) or ""
        summary["content"] = content
        calls = getattr(event, "tool_calls", None) or []
        if calls:
            # Arguments are kept whole: cutting them leaves JSON that no longer parses, and the
            # tool behind a `call_tool` wrapper is lost.
            summary["tool_calls"] = [
                {
                    "id": getattr(call, "id", None),
                    "name": _tool_name(call),
                    # "mcp" for an MCP server's tool, "truefoundry-system" for the harness's own
                    # (exec, call_tool, create_sub_agent, ...).
                    "type": getattr(getattr(call, "tool_info", None), "type", None),
                    "arguments": getattr(getattr(call, "function", None), "arguments", "") or "",
                }
                for call in calls
            ]
    elif event.type == "tool.response":
        summary["tool_call_id"] = getattr(event, "tool_call_id", None)
        summary["content"] = (getattr(event, "content", None) or "")[:4000]
    elif event.type == "thread.created":
        summary["title"] = getattr(event, "title", None)
    return summary


def tool_labels(transcript: list[dict]) -> tuple[list[str], list[str]]:
    """Every tool call as `tool args -> start of result`, plus the MCP calls sandbox commands made."""
    results = {
        entry.get("tool_call_id"): entry.get("content", "")
        for entry in transcript
        if entry.get("type") == "tool.response"
    }
    labels: list[str] = []
    sandbox: list[str] = []
    for entry in transcript:
        for call in entry.get("tool_calls", []):
            raw = call.get("arguments", "")
            result = results.get(call.get("id"))
            for name in _effective_tool_names(call["name"], raw):
                labels.append(name + (RESULT_SEPARATOR + _result_snippet(result) if result is not None else ""))
            if call["name"] == "exec":
                try:
                    command = str(json.loads(raw or "{}").get("command") or "")
                except (json.JSONDecodeError, TypeError, AttributeError):
                    command = str(raw)
                sandbox += sandbox_tool_calls(command)
    return labels, sandbox


def mcp_invocations(transcript: list[dict]) -> list[dict]:
    """Every MCP tool the agent invoked, direct or through `call_tool`: {id, tool, result}.

    The harness's own tools (exec, create_sub_agent, get_tool_info, ...) are not MCP tools and are
    left out; so are calls the harness rejected because no such tool exists.
    """
    results = {
        entry.get("tool_call_id"): entry.get("content", "")
        for entry in transcript
        if entry.get("type") == "tool.response"
    }
    found = []
    for entry in transcript:
        for call in entry.get("tool_calls", []):
            if call["name"] == "call_tool":
                tool = tool_label_name(_effective_tool_names("call_tool", call.get("arguments", ""))[0])
                if tool == "call_tool":
                    continue
            elif call.get("type") == "mcp":
                tool = call["name"]
            else:
                continue
            result = results.get(call.get("id"))
            if result is not None and NOT_IN_TOOL_MAPPING in result:
                continue
            found.append({"id": call.get("id"), "tool": tool, "result": result})
    return found


def run_question(
    client: TrueForge,
    agent: dict,
    question: str,
    *,
    question_id: str,
    trial: int = 0,
    base_url: str = "",
    on_approval: str = "allow",
    clarification_reply: str = DEFAULT_CLARIFICATION_REPLY,
    max_rounds: int = 4,
    max_reconnects: int = 8,
    on_progress: Callable[[str], None] | None = None,
) -> AgentRun:
    """Ask one question and return the agent's final answer plus diagnostics.

    `agent` is passed straight to sessions.create, so either {"name": ...} for a
    saved agent or {"spec": {...}} for an inline one.
    """
    run = AgentRun(question_id=question_id, trial=trial)
    started = time.monotonic()

    try:
        session = client.sessions.create(
            agent=agent,
            metadata={"eval": "tfy-agent-eval", "question_id": question_id, "trial": str(trial)},
        )
        run.session_id = session.data.id
        if base_url:
            run.session_url = session_url(base_url, session.data.id)

        events: dict[str, Any] = {}
        order: list[str] = []
        turn_input: list[dict] = [{"type": "user.message", "content": question}]

        for round_index in range(max_rounds):
            run.rounds = round_index + 1
            final_state, pending_approvals, pending_responses = _stream_turn(
                client,
                session.data.id,
                turn_input,
                run=run,
                events=events,
                order=order,
                max_reconnects=max_reconnects,
                on_progress=on_progress,
            )

            run.transcript = [_event_summary(events[eid]) for eid in order]
            run.tool_calls, run.sandbox_tool_calls = tool_labels(run.transcript)

            status = getattr(final_state, "status", None)
            metrics = getattr(final_state, "metrics", None)
            if metrics is not None:
                # turn.done reports one turn, so a resumed run must accumulate.
                for key, value in (
                    metrics.dict() if hasattr(metrics, "dict") else dict(metrics)
                ).items():
                    if isinstance(value, (int, float)):
                        run.metrics[key] = (run.metrics.get(key) or 0) + value

            if status == "running":
                run.status = "timeout"
                run.failure = "infra:poll_timeout"
                run.error = f"turn still running after {POLL_TIMEOUT_S}s of polling"
                run.answer = _final_answer(None, events, order)
                # Stop it, so a retry does not run alongside an abandoned turn.
                try:
                    client.sessions.cancel(session_id=session.data.id)
                except Exception:  # noqa: BLE001 - best effort; the run is already a failure
                    pass
                break

            if status in (None, "error", "cancelled"):
                run.status = status or "error"
                reason = getattr(final_state, "reason", None)
                reason = str(getattr(reason, "value", reason) or "")
                run.error = str(getattr(final_state, "message", None) or reason or "stream ended without turn.done")
                run.failure = (
                    "agent:server_timeout" if reason == "server-execution-timeout"
                    else "infra:cancelled" if status == "cancelled"
                    else "infra:turn_error"
                )
                break

            if not pending_approvals and not pending_responses:
                # Pauses we missed while disconnected are still listed on the turn's state.
                for action in getattr(final_state, "required_actions", None) or []:
                    action_type = getattr(action, "type", None)
                    if action_type == "tool.approval_required":
                        pending_approvals.append(action)
                    elif action_type == "tool.response_required":
                        pending_responses.append(action)
                    elif action_type == "mcp.auth_required":
                        run.mcp_auth_required.extend(
                            str(getattr(server, "name", server)) for server in getattr(action, "mcp_servers", None) or []
                        )
                if status == "paused" and not (pending_approvals or pending_responses or run.mcp_auth_required):
                    run.status = "paused"
                    run.failure = "infra:unresumable"
                    run.error = "turn paused but its pending actions could not be read"
                    run.answer = _final_answer(None, events, order)
                    break

            if run.mcp_auth_required:
                run.status = "paused"
                run.failure = "infra:mcp_auth"
                run.error = f"MCP auth required: {', '.join(sorted(set(run.mcp_auth_required)))}"
                run.answer = _final_answer(final_state, events, order)
                break

            if not pending_approvals and not pending_responses:
                run.status = "done"
                run.answer = _final_answer(final_state, events, order)
                break

            turn_input = _resume_input(
                run, events, pending_approvals, pending_responses, on_approval, clarification_reply
            )
            if not turn_input:
                run.status = "paused"
                run.failure = "infra:unresumable"
                run.error = "turn paused but no resumable action could be built"
                run.answer = _final_answer(final_state, events, order)
                break
            if on_progress:
                on_progress(f"{question_id}: resuming after pause (round {run.rounds})")
        else:
            # Keep whatever the agent did say, so a run that ran out of rounds is
            # still inspectable instead of landing in the report as an empty row.
            run.status = "paused"
            run.failure = "agent:stalled"
            run.error = f"still paused after {max_rounds} rounds"
            run.answer = _final_answer(None, events, order)

        if run.status == "done" and not run.answer.strip():
            run.status = "error"
            run.failure = "agent:empty_answer"
            run.error = "agent returned an empty answer"
        elif run.status == "done" and STEP_LIMIT_MARKER in run.answer.lower():
            run.failure = "agent:step_limit"
            run.error = "agent hit the iteration limit"

    except AbortRun:
        raise
    except Exception as exc:  # noqa: BLE001 - one bad question must not kill the suite
        run.status = "error"
        run.failure = "infra:exception"
        run.error = f"{type(exc).__name__}: {exc}"

    run.duration_s = time.monotonic() - started
    return run


def _stream_turn(
    client: TrueForge,
    session_id: str,
    turn_input: list[dict],
    *,
    run: AgentRun,
    events: dict[str, Any],
    order: list[str],
    max_reconnects: int,
    on_progress: Callable[[str], None] | None,
) -> tuple[Any, list[Any], list[Any]]:
    """Stream one turn to completion, re-attaching if the connection drops.

    Returns the terminal turn state plus any pauses that need a response.
    """
    pending_approvals: list[Any] = []
    pending_responses: list[Any] = []
    final_state: Any = None
    turn_id: str | None = None
    last_sequence: int | None = None
    reconnects = 0
    started = time.monotonic()

    def open_initial() -> Any:
        return client.sessions.create_turn_stream(session_id=session_id, input=turn_input)

    def open_resume() -> Any:
        return client.sessions.subscribe_to_turn(
            session_id=session_id, turn_id=turn_id, after_sequence_number=last_sequence
        )

    open_stream = open_initial

    while True:
        try:
            for meta in open_stream().with_metadata():
                if meta.id is not None:
                    try:
                        last_sequence = int(meta.id)
                    except (TypeError, ValueError):
                        pass
                event = meta.data

                if is_event_delta(event):
                    base = events.get(event.id)
                    if base is not None:
                        merge_event_delta(base, event)
                    continue

                if event.id not in events:
                    order.append(event.id)
                events[event.id] = event

                if event.type == "turn.created":
                    turn_id = event.turn_id
                    if turn_id not in run.turn_ids:
                        run.turn_ids.append(turn_id)
                elif event.type == "thread.created":
                    run.subagents.append(str(getattr(event, "title", "") or event.thread_id))
                elif event.type == "tool.approval_required":
                    pending_approvals.append(event)
                elif event.type == "tool.response_required":
                    pending_responses.append(event)
                elif event.type == "mcp.auth_required":
                    run.mcp_auth_required.extend(
                        str(getattr(server, "name", server))
                        for server in getattr(event, "mcp_servers", None) or []
                    )
                elif event.type == "turn.done":
                    final_state = event.state
            break
        except httpx.TransportError as exc:
            # Without a turn id there is nothing to re-attach to, and an exhausted
            # budget means the drop is not transient - let the caller retry.
            if turn_id is None or reconnects >= max_reconnects:
                raise
            # A turn this old is dead, not slow; re-attaching would wait on it again.
            if time.monotonic() - started > POLL_TIMEOUT_S:
                try:
                    client.sessions.cancel(session_id=session_id)
                except Exception:  # noqa: BLE001 - best effort; the caller retries on a new session
                    pass
                raise
            delay = RECONNECT_BACKOFF_S[min(reconnects, len(RECONNECT_BACKOFF_S) - 1)]
            reconnects += 1
            run.reconnects += 1
            if on_progress:
                on_progress(
                    f"{run.question_id}: stream dropped ({type(exc).__name__}), "
                    f"re-attaching in {delay}s (attempt {reconnects}/{max_reconnects})"
                )
            time.sleep(delay)
            open_stream = open_resume

    if final_state is None and turn_id is not None:
        # The turn very likely finished while we were disconnected, so the live
        # buffer had no turn.done left to replay. Ask for the state directly.
        final_state = _poll_turn_state(client, session_id, turn_id)

    return final_state, pending_approvals, pending_responses


def _poll_turn_state(client: TrueForge, session_id: str, turn_id: str) -> Any:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while True:
        state = client.sessions.get_turn(session_id=session_id, turn_id=turn_id).data.state
        if getattr(state, "status", None) in SETTLED_STATUSES:
            return state
        if time.monotonic() >= deadline:
            return state
        time.sleep(POLL_INTERVAL_S)


def run_question_with_retries(
    client: TrueForge,
    agent: dict,
    question: str,
    *,
    retries: int = 2,
    on_progress: Callable[[str], None] | None = None,
    **kwargs: Any,
) -> AgentRun:
    """Ask a question, retrying from a clean session on transient failures.

    MCP servers time out and streams get dropped often enough on this tenant that
    a single failure should not become a reported eval result. Only platform failures
    are retried: an agent that loops, stalls or says nothing does it again, and an
    MCP server that needs a login still needs one.
    """
    attempt = 0
    spent: dict[str, float] = {}
    earlier: list[AgentRun] = []
    while True:
        run = run_question(client, agent, question, on_progress=on_progress, **kwargs)
        run.attempts = attempt + 1
        run.earlier_attempts = earlier
        for key, value in spent.items():
            run.metrics[key] = run.metrics.get(key, 0) + value
        transient = run.failure in INFRA_FAILURES and run.failure != "infra:mcp_auth"
        if not transient or attempt >= retries:
            return run
        spent = {key: value for key, value in run.metrics.items() if isinstance(value, (int, float))}
        earlier = earlier + [run]
        attempt += 1
        if on_progress:
            on_progress(
                f"{run.question_id}: {run.status} ({run.error}); "
                f"retrying from a new session ({attempt}/{retries})"
            )
        time.sleep(5)


def _final_answer(final_state: Any, events: dict[str, Any], order: list[str]) -> str:
    output = getattr(final_state, "output", None)
    content = getattr(output, "content", None)
    if content:
        return str(content)
    # turn.done carries no output when the turn ended on a tool call; fall back to
    # the last thing the root agent actually said.
    for event_id in reversed(order):
        event = events[event_id]
        if (
            event.type == "model.message"
            and getattr(event, "thread_id", None) == "main"
            and (getattr(event, "content", None) or "").strip()
        ):
            return str(event.content)
    return ""


def _resume_input(
    run: AgentRun,
    events: dict[str, Any],
    pending_approvals: list[Any],
    pending_responses: list[Any],
    on_approval: str,
    clarification_reply: str,
) -> list[dict]:
    resume: list[dict] = []

    for pending in pending_approvals:
        for ref in getattr(pending, "tool_calls", None) or []:
            message = events.get(getattr(ref, "source_event_id", ""))
            call = _find_call(message, ref.id) if message is not None else None
            run.approvals_granted.append(f"{_tool_name(call) if call else 'unknown'}:{on_approval}")
            run.approval_call_ids.append(ref.id)
            approval = (
                {"status": "allow"}
                if on_approval == "allow"
                else {"status": "deny", "reason": "denied by eval harness"}
            )
            resume.append(
                {
                    "type": "user.tool_approval",
                    "thread_id": pending.thread_id,
                    "tool_call_id": ref.id,
                    "approval": approval,
                }
            )

    for pending in pending_responses:
        for ref in getattr(pending, "tool_calls", None) or []:
            message = events.get(getattr(ref, "source_event_id", ""))
            call = _find_call(message, ref.id) if message is not None else None
            is_secret = call is not None and _tool_name(call) == SECRET_TOOL
            if call is not None:
                (run.secrets_requested if is_secret else run.clarifications_asked).append(_question_text(call))
            resume.append(
                {
                    "type": "user.tool_response",
                    "thread_id": pending.thread_id,
                    "tool_call_id": ref.id,
                    "content": SECRET_REFUSAL if is_secret else clarification_reply,
                }
            )

    return resume
