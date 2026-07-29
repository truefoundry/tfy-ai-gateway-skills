---
name: budget-limiting-v2
description: Budget Limiting V2 — independent tenant- and team-scoped budget rules with multi-period and lifetime limits. Use V2 for all budget work.
---

**Budget Limiting V2** controls LLM spend with independent budget rules. Use V2 for all budget work — V1 (`gateway-budget-config`) is deprecated (see `ai-gateway/references/budget-limiting.md`).

**Always read the docs first.** For any V2 budget query: first call `get_page_layout` on https://www.truefoundry.com/docs/ai-gateway/budget-limiting-v2 to see its section anchors, then `get_section_content` on the section(s) you need (schema reference, examples, migration). The docs are the source of truth for the current schema and worked examples.

Two things to know:

- **One rule = one manifest.** Each budget rule is its own manifest, created and updated independently by `name`. To create N rules, call `apply_manifest` N times, each with a unique `name`.
- **Independent, all-must-pass.** Rules have no ordering — every matching rule is evaluated and the request is blocked if *any* is over budget. To exempt a group from a broad default, use a `not_in` filter.

## Scopes

Set by `type`: `tenant-budget-config` (tenant-wide, managed by tenant admins) or `team-budget-config` (a single team — add required `team_name: <name>`, managed by tenant admins and that team's managers). Team scope cannot filter `when.subjects.teams`.

## Reading existing rules (Read Flow)

Use **`list_gateway_budgets`** to read V2 rules. Because each V2 rule is its own manifest, there is no single config object to fetch — **`get_gateway_config` does not work for V2** (it only serves the V1 `gateway-budget-config`). Check the tool's schema for the scope/team filter arguments it accepts.

Use it for every V2 read: listing what budgets exist, checking for overlapping rules before creating a new one, and reporting spend. When the response carries usage data (current spend, percent consumed, remaining, period start), present that alongside the limits — and for per-entity rules, which entities are over budget.

## Creating/Updating rules (Write Flow)

Always confirm the exact schema with `get_manifest_json_schema` before building — the field names below are strict.

1. Call `get_manifest_json_schema` for the type; call `list_gateway_budgets` to review existing rules — a new rule stacks on any overlapping one.
2. Gather scope, filters (`when`), limits, `applies_to`, `mode`, and optional alerts — use `ask_user_question` for choices.
3. For **each** rule: build one manifest (top-level `name`) → `validate_manifest` → `apply_manifest`.

### Manifest Structure

```yaml
name: <unique-rule-name>       
type: tenant-budget-config           # or team-budget-config
team_name: <team-name>               # REQUIRED for team-budget-config only
mode: enforce                        # enforce = block; audit = warn-only
limits:                              # one or more; any combination is allowed, incl. cost_per_lifetime
  cost_per_day: <n>                  # also cost_per_week / _month / _quarter / _lifetime
applies_to:                          # discriminated by `type`
  type: aggregate                    # aggregate | per-user | per-model | per-virtual-account | metadata
  metadata: <key>                    # REQUIRED only when type: metadata (the key to bucket by)
when:                                # optional; omit or use `when: {}` to match everything in scope
  subjects:
    users: { in: [<email>] }         # in / not_in (values are bare, e.g. alice@x.com)
    teams: { in: [<team>] }          # tenant scope only
    virtual_accounts: { in: [<va>] }
  models: { in: [<account/model>] }
  provider_accounts: { in: [<account>] }
  metadata:
    <key>: { in: [<value>] }
alerts:
  thresholds: [75, 90, 95, 100]
  notification_target:
    - type: email                    # email | slack-webhook | slack-bot | pagerduty | ms-teams-webhook
      notification_channel: <fqn>
      to_emails: [<email>]           # email requires to_emails; slack-bot requires channels: ["#chan"]
```

**Overrides** (optional, per-entity `applies_to` only) live **inside `applies_to`**, keyed by the entity type — not at the top level:

```yaml
applies_to:
  type: per-user                     # per-model / per-virtual-account / metadata analogous
  overrides:
    - users: [<email>]               # per-model → models: [...]; per-virtual-account → virtual_accounts: [...]; metadata → metadata_values: [...]
      limits: { cost_per_day: <n> }  # replaces ALL base periods for those entities
```

Gotchas: `applies_to.type` is hyphenated (`per-user`, `per-model`, `per-virtual-account`) except `aggregate` and `metadata`, and it cannot be changed after the rule is created — to re-partition a budget, create a new rule and disable the old one; `type: metadata` needs a `metadata: <key>` field; there is no `send_to` field on alerts; usage counts from rule creation, not from the start of the current period, so earlier spend is never backfilled; for metadata keys you don't know, discover them from live data (see `ai-gateway/references/observability.md`) — don't ask the user.

## Checklist

- [ ] Did I read existing rules with `list_gateway_budgets` (not `get_gateway_config`)?
- [ ] One rule per manifest, each with a unique `name`?
- [ ] Does `when` use the nested `in`/`not_in` form (with `virtual_accounts`, not `virtualaccounts`)?
- [ ] Is `applies_to.type` one of `aggregate`/`per-user`/`per-model`/`per-virtual-account`/`metadata` (and `metadata:` set for the metadata type)?
- [ ] For team scope, is `team_name` set and confirmed to exist?
- [ ] Validated before applying, and checked existing rules for overlap?

## Migrating from V1

V1 is a single tenant-wide config with an ordered `rules[]`; V2 is one manifest per rule. Migrate every V1 rule to a **`tenant-budget-config`** (V1 was always tenant-scoped).

1. Fetch V1 with `get_gateway_config` (`type: gateway-budget-config`) and audit each rule — this is the one place `get_gateway_config` still applies. Also call `list_gateway_budgets` to see what has already been migrated.
2. Recreate each `rules[]` entry as its own `tenant-budget-config` manifest:
   - `id` → `name`
   - `audit_mode: false/true` → `mode: enforce/audit`
   - `budget_applies_per: ['user'|'model'|'virtualaccount']` → `applies_to.type: per-user`/`per-model`/`per-virtual-account`; `['metadata.<key>']` → `applies_to: { type: metadata, metadata: <key> }`; omitted → `applies_to: { type: aggregate }`
   - `limit_to` + `unit` → `limits: { <unit>: <limit_to> }`
   - flat `when` (`['user:a@x','team:eng']`) → nested `in`/`not_in` (`subjects.users.in: [a@x]`, `subjects.teams.in: [eng]`)
3. V2 has no ordering — if a V1 rule was an override above a default, exclude that group from the default with `not_in` (or use per-entity `overrides` inside `applies_to`); otherwise both limits apply and the tightest wins.
4. Create V2 rules in `mode: audit`, verify for a full period, switch to `enforce`, then disable the V1 rules (both run in parallel during the transition).

For more info: `search_docs` with "budget limiting v2", "migrate budget limiting".
