"""Seed the neutral devtest fixtures the eval cases name (see evals/FIXTURES.md).

    cd evals && python -m runner.seed_fixtures

Idempotent: teams and budgets apply by name, grants that exist are skipped. Uses `tfy apply`, so the
tfy CLI must be installed; TFY_API_KEY must be able to manage teams and assign roles, and
EVAL_FIXTURE_MANAGER is the email of the user who manages the fixture teams.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

import httpx

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


def main() -> None:
    host, token = os.environ["ASK_TFY_HOST"].rstrip("/"), os.environ["TFY_API_KEY"]
    manager = os.environ["EVAL_FIXTURE_MANAGER"]
    api = httpx.Client(base_url=f"{host}/api/svc", headers={"Authorization": f"Bearer {token}"}, timeout=120)

    for name, description in TEAMS.items():
        apply(host, {"type": "team", "name": name, "description": description, "managers": [manager]})
    apply(host, BUDGET)

    teams = {t.get("teamName") or t.get("name"): t["id"]
             for t in api.get("/v1/teams/user", params={"includeMembership": "false"}).json()["data"]}
    user = next(u["id"] for u in api.get("/v1/users", params={"query": TEST_USER}).json()["data"]
                if u.get("email") == TEST_USER)
    account = find_account(api, PROVIDER_ACCOUNT)
    existing = {(g["subjectType"], g["subjectId"], g["roleId"]) for g in api.get(
        "/v2/authorization/grants", params={"resourceType": "provider-account", "resourceId": account}).json()["data"]}
    grants = [
        {"resourceType": "provider-account", "resourceId": account, "subjectType": kind, "subjectId": subject,
         "roleId": ROLE}
        for kind, subject in (("user", user), ("team", teams["eval-engineering"]))
        if (kind, subject, ROLE) not in existing
    ]
    if grants:
        api.post("/v2/authorization", json={"grants": grants}).raise_for_status()
    print(f"fixtures ready; {len(grants)} grant(s) created")


def apply(host: str, manifest: dict) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(manifest, handle)
    subprocess.run(["tfy", "apply", "-f", handle.name], check=True, env=os.environ | {"TFY_HOST": host})


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
