"""Seed the neutral devtest fixtures the eval cases name (see evals/FIXTURES.md).

    cd evals && python -m runner.seed_fixtures

Idempotent: entities apply by name, grants that exist are skipped. Then sends the requests whose
traces the trace cases ask about, waits until each trace is queryable and failed the way its case
says, and writes their ids, times, senders and errors to runs/fixtures.json, which the runner fills
into the cases' {{trace.<name>.<field>}} placeholders. Traces expire, so this runs before every run.

TFY_API_KEY must be able to manage teams, users,
provider accounts, budgets and rate limits and assign roles; its subject sends the traces and is
granted access to the eval- models. EVAL_FIXTURE_MANAGER is the email of the user who manages the
fixture teams and accounts; ASK_TFY_TENANT is the tenant name.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from .cases import FIXTURES_FILE

TEAMS = {
    "eval-engineering": "Ask TFY eval fixture: holds one grant so its access can be exported (s27, s47)",
    "eval-platform": "Ask TFY eval fixture: no access, for grant cases (s45)",
    "eval-budget": "Ask TFY eval fixture: has an audit-only monthly budget (s25)",
}
BUDGET = {
    "name": "eval-budget-monthly", "type": "team-budget-config", "team_name": "eval-budget", "mode": "audit",
    "limits": {"cost_per_month": 100}, "applies_to": {"type": "aggregate"},
}
PROVIDER_ACCOUNT = "openai-main"
TEST_USER = "test@example.com"
ROLE = "provider-account-access"
CAROL = "eval-carol@example.com"
CAROL_ROLE = "read-only-member"

# The one cheap chat model on devtest that answers; every eval- virtual model routes to it.
WORKING_MODEL = "tfy-ai-openrouter/openai-gpt-5.4-nano"
LIMITS = [
    {"name": "eval-budget-enforce", "type": "tenant-budget-config", "mode": "enforce",
     "limits": {"cost_per_day": 0.000001}, "applies_to": {"type": "aggregate"},
     "when": {"virtual_models": {"in": ["eval-vm/budget"]}}},
    {"name": "eval-rate-limit", "type": "tenant-rate-limit-config/model", "mode": "enforce",
     "limits": {"requests_per_minute": 1}, "applies_to": {"type": "aggregate"},
     "when": {"models": {"in": ["eval-vm/rate-limit"]}}, "log_request_body_on_block": False},
]
DOCS_MCP_URL = "https://global.truefoundry.com/ask-ai/tfy-docs-mcp"
GATEWAY_SYNC_S = 60
LIMIT_SYNC_TIMEOUT_S = 180
PII = "My SSN is 123-45-6789, my card is 4111 1111 1111 1111 and my email is john.doe@gmail.com"


@dataclass(frozen=True)
class Trace:
    """One request whose trace a case asks about, and the span error that proves it failed as intended."""

    name: str
    model: str
    status: int
    error_type: str
    body: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    content: str = "Say hi"
    # Budgets and rate limits block only once earlier requests have counted.
    attempts: int = 1


NOT_FOUND = Trace("not_found", "eval-openai/o4-mini", 403, "tfy-model-not-found")
TRACES = [
    NOT_FOUND,
    Trace("provider_400", "eval-vm/chat", 400, "request-failure-400", body={"logprobs": True, "top_logprobs": 50}),
    Trace("guardrail", "eval-vm/chat", 400, "tfy-input-guardrail", content=PII,
          headers={"X-TFY-GUARDRAILS": json.dumps({"input_guardrails": ["tfy-guardrail/pii"]})}),
    Trace("budget", "eval-vm/budget", 429, "tfy-budget-limit", attempts=3),
    Trace("rate_limit", "eval-vm/rate-limit", 429, "tfy-rate-limit", attempts=3),
    Trace("fallback", "eval-vm/fallback", 200, "request-failure-401"),
]
TRACE_BY_NAME = {trace.name: trace for trace in TRACES}


def main() -> None:
    host, token = os.environ["ASK_TFY_HOST"].rstrip("/"), os.environ["TFY_API_KEY"]
    manager, tenant = os.environ["EVAL_FIXTURE_MANAGER"], os.environ["ASK_TFY_TENANT"]
    headers = {"Authorization": f"Bearer {token}"}
    api = httpx.Client(base_url=f"{host}/api/svc", headers=headers, timeout=120)
    gateway = httpx.Client(base_url=f"{host}/api/llm", headers=headers, timeout=120)

    for name, description in TEAMS.items():
        apply(api, {"type": "team", "name": name, "description": description, "managers": [manager]})
    apply(api, BUDGET)
    seed_grants(api)
    seed_carol(api, tenant)

    # The model-not-found request needs no access, and its trace names the subject the token acts as.
    sent = {NOT_FOUND.name: send(gateway, NOT_FOUND)}
    sender = wait_for(api, sent)[NOT_FOUND.name]["subject"]
    for manifest in provider_accounts(manager):
        apply(api, manifest)
        grant_access(api, find_account(api, manifest["name"]), *sender)
    for manifest in LIMITS:
        apply(api, manifest)
    apply(api, docs_proxy(manager))
    # The gateway loads applied config asynchronously; earlier requests may route by the old one.
    time.sleep(GATEWAY_SYNC_S)

    # A trace that cannot be produced costs only the cases that name it: the runner skips those.
    unavailable: dict[str, str] = {}
    for trace in TRACES:
        if trace is NOT_FOUND:
            continue
        try:
            sent[trace.name] = send(gateway, trace)
        except SystemExit as exc:
            unavailable[f"trace.{trace.name}"] = str(exc)
    found = wait_for(api, sent, strict=False)
    unavailable |= {f"trace.{name}": f"trace {sent[name]} was not queryable with span error "
                    f"{TRACE_BY_NAME[name].error_type} after the wait" for name, info in found.items() if not info}
    # The agent reads traces through SQL, which lags the spans API by minutes.
    in_sql = wait_for_sql(api, {name: info for name, info in found.items() if info})
    for name, info in list(found.items()):
        if info and name not in in_sql:
            unavailable[f"trace.{name}"] = f"trace {info['id']} never showed up in the SQL traces table"
            found[name] = None
    values = {f"trace.{name}.{key}": value for name, trace in found.items() if trace
              for key, value in trace.items() if key != "subject"}
    FIXTURES_FILE.parent.mkdir(exist_ok=True)
    FIXTURES_FILE.write_text(json.dumps({"seeded_at": datetime.now(timezone.utc).isoformat(), "values": values,
                                         "unavailable": unavailable}, indent=2) + "\n")
    print(f"fixtures ready; {sum(1 for info in found.values() if info)} traces written to {FIXTURES_FILE}")
    for name, reason in unavailable.items():
        print(f"WARNING: {name} not seeded, its cases will be skipped: {reason}")


def apply(api: httpx.Client, manifest: dict) -> None:
    response = api.put("/v1/apply", json={"manifest": manifest})
    if response.is_error:
        raise SystemExit(f"applying {manifest['type']} {manifest['name']} failed: {response.status_code} "
                         f"{response.text[:500]}")


def seed_grants(api: httpx.Client) -> None:
    teams = {t.get("teamName") or t.get("name"): t["id"]
             for t in api.get("/v1/teams/user", params={"includeMembership": "false"}).json()["data"]}
    user = user_id(api, TEST_USER)
    account = find_account(api, PROVIDER_ACCOUNT)
    grant_access(api, account, "user", user)
    grant_access(api, account, "team", teams["eval-engineering"])


def grant_access(api: httpx.Client, account: str, kind: str, subject: str) -> None:
    existing = {(g["subjectType"], g["subjectId"], g["roleId"]) for g in api.get(
        "/v2/authorization/grants", params={"resourceType": "provider-account", "resourceId": account}).json()["data"]}
    if (kind, subject, ROLE) not in existing:
        api.post("/v2/authorization", json={"grants": [
            {"resourceType": "provider-account", "resourceId": account, "subjectType": kind, "subjectId": subject,
             "roleId": ROLE}]}).raise_for_status()


def seed_carol(api: httpx.Client, tenant: str) -> None:
    """A user holding read-only-member, for the role-change case (s58)."""
    # Register only when missing: with Manual provisioning off, registering an existing user is a
    # 403, not a 409.
    if find_user(api, CAROL) is None:
        registered = api.post("/v1/users/register", json={"email": CAROL, "sendInviteEmail": False})
        if registered.is_error and registered.status_code != 409:
            raise SystemExit(f"registering {CAROL} failed: {registered.status_code} {registered.text[:300]}. "
                             "Turn on Manual provisioning for the tenant, or add the user once by hand.")
    carol = user_id(api, CAROL)
    role = next(r["id"] for r in api.get("/v1/role").json() if r.get("name") == CAROL_ROLE)
    held = api.get("/v2/authorization/grants", params={"subjectType": "user", "subjectId": carol}).json()["data"]
    if not any(g["roleId"] == role and g["resourceType"] == "tenant" for g in held):
        api.post("/v2/authorization", json={"grants": [
            {"resourceType": "tenant", "resourceFqn": tenant, "subjectType": "user", "subjectId": carol,
             "roleId": role}]}).raise_for_status()


def provider_accounts(manager: str) -> list[dict]:
    collaborators = [{"role_id": "provider-account-manager", "subject": f"user:{manager}"}]

    def virtual(name: str, *targets: str) -> dict:
        return {"name": name, "type": "integration/model/virtual", "model_types": ["chat"],
                "routing_config": {"type": "priority-based-routing", "load_balance_targets": [
                    {"target": target, "priority": priority, "fallback_candidate": True,
                     "fallback_status_codes": ["401", "403", "404", "429", "500", "502", "503"]}
                    for priority, target in enumerate(targets)]}}

    return [
        {"name": "eval-openai", "type": "provider-account/openai",
         # Invalid on purpose: eval-openai/primary always fails with 401, so eval-vm/fallback falls back.
         "auth_data": {"type": "api-key", "api_key": "sk-eval-invalid"},
         "collaborators": collaborators,
         "integrations": [{"name": "primary", "type": "integration/model/openai", "model_id": "gpt-4.1-nano",
                           "model_types": ["chat"]}]},
        {"name": "eval-vm", "type": "provider-account/virtual-model", "collaborators": collaborators,
         "integrations": [virtual("chat", WORKING_MODEL), virtual("fallback", "eval-openai/primary", WORKING_MODEL),
                          virtual("budget", WORKING_MODEL), virtual("rate-limit", WORKING_MODEL)]},
    ]


def docs_proxy(manager: str) -> dict:
    """An MCP server whose manifest still lists collaborators, for the move-to-grants case (s48)."""
    return {"name": "eval-docs-proxy", "type": "mcp-server/remote", "url": DOCS_MCP_URL,
            "description": "Ask TFY eval fixture: its manifest still carries a collaborators list (s48)",
            "collaborators": [{"role_id": "mcp-server-manager", "subject": f"user:{manager}"}]}


def send(gateway: httpx.Client, trace: Trace) -> str:
    """The trace id of the request that came back with the trace's status."""
    statuses = []
    # A limit applied moments ago may not have reached every gateway pod: keep sending until it does.
    deadline = time.monotonic() + (LIMIT_SYNC_TIMEOUT_S if trace.attempts > 1 else 0)
    while True:
        for _ in range(trace.attempts):
            response = gateway.post("/chat/completions", headers=trace.headers, json={
                "model": trace.model, "messages": [{"role": "user", "content": trace.content}], "max_tokens": 20,
                **trace.body})
            statuses.append(response.status_code)
            if response.status_code == trace.status:
                target = json.loads(base64.b64decode(response.headers["x-tfy-feedback-target-id"]))
                return target["traceId"]
        if time.monotonic() > deadline:
            raise SystemExit(f"{trace.name}: {trace.model} returned {statuses}, expected {trace.status}: "
                             f"{response.text[:300]}")
        time.sleep(20)


def wait_for(api: httpx.Client, sent: dict[str, str], timeout: float = 600,
             strict: bool = True) -> dict[str, dict | None]:
    """Each trace once queryable: id, time, sender and the error of the span that shows the failure.
    Past the timeout, strict exits; otherwise a trace still missing maps to None."""
    start = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    deadline = time.monotonic() + timeout
    while True:
        spans = api.post("/v1/spans/query", json={
            "startTime": start, "traceIds": list(sent.values()), "dataRoutingDestination": "default",
            "limit": 200}).raise_for_status().json()["data"]
        found = {name: describe(TRACE_BY_NAME[name], trace_id, [s for s in spans if s["traceId"] == trace_id])
                 for name, trace_id in sent.items()}
        if all(found.values()):
            return found
        if time.monotonic() > deadline:
            if not strict:
                return found
            raise SystemExit(f"traces not queryable or not failing as intended after {timeout:.0f}s: "
                             + ", ".join(f"{name} {sent[name]}" for name, info in found.items() if not info))
        time.sleep(15)


def wait_for_sql(api: httpx.Client, found: dict[str, dict], timeout: float = 900) -> set[str]:
    """The traces `gateway_execute_sql` can see, polled until all of them are or the timeout passes."""
    if not found:
        return set()
    table = api.get("/v1/session/context").raise_for_status().json()["tracesTable"]
    day = min(info["time"][:10] for info in found.values())
    ids = ", ".join(f"'{info['id']}'" for info in found.values())
    query = (f'SELECT DISTINCT "TraceId" FROM "default"."{table}" '
             f"WHERE \"Date\" >= '{day}' AND \"TraceId\" IN ({ids}) LIMIT 100")
    deadline = time.monotonic() + timeout
    while True:
        rows = api.post("/v1/llm-gateway/observability/execute-sql",
                        json={"query": query}).raise_for_status().json()["data"]
        seen = {row["TraceId"] for row in rows}
        visible = {name for name, info in found.items() if info["id"] in seen}
        if len(visible) == len(found) or time.monotonic() > deadline:
            return visible
        time.sleep(20)


def describe(trace: Trace, trace_id: str, spans: list[dict]) -> dict | None:
    failed = [s for s in spans if s.get("spanAttributes", {}).get("tfy.error_type") == trace.error_type]
    if not failed:
        return None
    when = min(datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00")) for s in spans)
    subject = spans[0]["createdBySubject"]
    return {
        "id": trace_id,
        "time": when.strftime("%Y-%m-%d %H:%M"),
        "epoch_ms": str(int(when.timestamp() * 1000)),
        "sender": subject["subjectSlug"],
        "subject": (subject["subjectType"], subject["subjectId"]),
        "error": failed[0].get("statusMessage") or failed[0]["spanAttributes"].get("tfy.error_message", ""),
    }


def find_user(api: httpx.Client, email: str) -> str | None:
    return next((u["id"] for u in api.get("/v1/users", params={"query": email}).json()["data"]
                 if u.get("email") == email), None)


def user_id(api: httpx.Client, email: str) -> str:
    found = find_user(api, email)
    if found is None:
        raise SystemExit(f"user {email} not found on the tenant")
    return found


def find_account(api: httpx.Client, name: str) -> str:
    offset = 0
    while True:
        page = api.get("/v1/provider-accounts", params={"limit": 500, "offset": offset}).json()["data"]
        for account in page:
            if account.get("name") == name:
                return account["id"]
        if len(page) < 500:
            raise SystemExit(f"provider account {name} not found")
        offset += 500


if __name__ == "__main__":
    main()
