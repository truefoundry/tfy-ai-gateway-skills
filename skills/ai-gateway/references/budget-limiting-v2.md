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

Set by `type`: `tenant-budget-config` (tenant-wide, managed by tenant admins) or `team-budget-config` (a single team — add `team: <name>`, managed by tenant admins and that team's managers).

## Creating/Updating rules (Write Flow)

1. Call `get_manifest_json_schema` for the type; call `get_gateway_config` (`type: tenant-budget-config` / `team-budget-config`) to review existing rules — a new rule stacks on any overlapping one.
2. Gather scope, filters (`when`), limits, `applies_to`, `mode`, and optional alerts — use `ask_user_question` for choices.
3. For **each** rule: build one manifest (top-level `name`) → `validate_manifest` → `apply_manifest`.

### Manifest Structure

```yaml
name: <unique-rule-name>
type: tenant-budget-config          # or team-budget-config (then also add: team: <name>)
mode: enforce                       # enforce = block; audit = warn-only
applies_to:
  type: aggregate                   # aggregate | user | model | virtualaccount | metadata
  key: <metadata-key>               # only when type: metadata
limits:                             # one or more periods
  cost_per_day: <n>                 # also cost_per_week / _month / _quarter / _lifetime (lifetime never resets)
when:                               # {} = everything in scope
  subjects:
    users: { in: [<bare-email>] }   # in / not_in; teams and virtualaccounts use the same shape
  models: { in: [<account/model>] }
  metadata:
    <key>: { in: [<value>] }
overrides:                          # per-entity rules only; replaces ALL base periods for that entity
  - subject: user:<email>           # prefixed here (unlike when.subjects, which are bare)
    limits: { cost_per_day: <n> }
alerts:
  thresholds: [75, 90, 95, 100]
  send_to: shared
  notification_target:
    - type: email                   # email | slack-webhook | slack-bot
      notification_channel: <fqn>
      to_emails: [<email>]          # per-user rules may use "{{user.email}}"
```

Gotchas: `mode` is `enforce` or `audit`; `applies_to.type: metadata` needs `key`; `when` subjects are **bare** but `overrides.subject` is **prefixed**; for metadata keys you don't know, discover them from live data (see `ai-gateway/references/observability.md`) — don't ask the user.

## Checklist

- [ ] One rule per manifest, each with a unique `name`?
- [ ] Does `when` use the nested `in`/`not_in` form?
- [ ] Is `mode` set, and for team scope is `team` set and confirmed to exist?
- [ ] Validated before applying, and checked existing rules for overlap?

## Migrating from V1

V1 is a single tenant-wide config with an ordered `rules[]`; V2 is one manifest per rule. Migrate every V1 rule to a **`tenant-budget-config`** (V1 was always tenant-scoped).

1. Fetch V1 with `get_gateway_config` (`type: gateway-budget-config`) and audit each rule.
2. Recreate each `rules[]` entry as its own `tenant-budget-config` manifest: `id`→`name`, `audit_mode`→`mode`, `budget_applies_per`→`applies_to`, `limit_to`+`unit`→`limits`, flat `when`→nested `in`/`not_in`.
3. V2 has no ordering — if a V1 rule was an override above a default, exclude that group from the default with `not_in` (or use `overrides`); otherwise both limits apply and the tightest wins.
4. Create V2 rules in `mode: audit`, verify for a full period, switch to `enforce`, then disable the V1 rules (both run in parallel during the transition).

For more info: `search_docs` with "budget limiting v2", "migrate budget limiting".
