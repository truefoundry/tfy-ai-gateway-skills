---
name: budget-limiting-v2
description: Budget Limiting V2 — independent tenant- and team-scoped budget rules with multi-period and lifetime limits. Use V2 for all budget work.
---

**Budget Limiting V2** controls LLM spend with independent budget rules. Use V2 for all budget work — V1 (`gateway-budget-config`) is deprecated (see `budget-limiting.md`).

This file is the source of truth for fields and validation rules. Read the docs only for worked examples or edge cases this file doesn't cover: `get_page_layout` on https://www.truefoundry.com/docs/ai-gateway/budget-limiting-v2, then `get_section_content` for the section you need. Migration notes are at https://www.truefoundry.com/docs/ai-gateway/budgetlimiting#migrating-to-budget-limiting-v2.

Two things to know:

- **One rule = one manifest.** Each budget rule is its own manifest, created and updated independently by `name`. To create N rules, call `apply_manifest` N times, each with a unique `name`. `apply_manifest` with an existing `name` **replaces** that budget. Before creating, confirm the name isn't in `list_gateway_budgets` output. If the apply response includes `existingManifest`, you overwrote a budget: tell the user.
- **Independent, all-must-pass.** Rules have no ordering — every matching rule is evaluated, and the request is blocked if any matching `enforce` rule is over budget (`audit` never blocks; `soft_enforce` blocks only when no other matching rule has room). To exempt a group from a broad default, use a `not_in` filter.

## Scopes

Set by `type`: `tenant-budget-config` (tenant-wide, managed by tenant admins) or `team-budget-config` (a single team — add required `team_name: <name>`, managed by tenant admins and that team's managers). Team scope: `when.subjects` allows only `users` and `virtual_accounts`. Scope (`type`/`team_name`) can't change after creation (403); recreate the budget instead.

## Reading existing rules (Read Flow)

Use **`list_gateway_budgets`** to read V2 rules. Each V2 rule is its own manifest, so **`get_gateway_config` does not work for V2** (for budgets it returns only the V1 `gateway-budget-config`). `list_gateway_budgets` takes optional `type` (`tenant-budget-config` | `team-budget-config`) and `team_name`, and returns results sorted by name. Non-admins see only budgets for teams they manage. So an empty or tenant-free result doesn't prove no tenant budgets exist; say so.

Use it to list budgets and check for overlap before creating one. It returns limits only, never spend.

**Spend:** `get_budget_usage` with a budget's `id` from `list_gateway_budgets` returns, per period, `limit`, `used`, `percentage` and `is_blocked` for its top spenders in its `applies_to` dimension (an aggregate budget has one entry with `entity: null`). For the caller's own budgets, call `get_my_budget_usage` (no arguments). Report the numbers as returned; never estimate them. Link `{controlPlaneUrl}/llm-gateway/policies/budget-limiting-v2` for more.

## Creating/Updating rules (Write Flow)

Read `write-rules.md` in the same batch.

1. In one batch: `get_manifest_json_schema` for the type, and `list_gateway_budgets` to review existing rules — a new rule stacks on any overlapping one.
2. Gather scope, filters (`when`), limits, `applies_to`, `mode`, and optional alerts — use `ask_user_question` for choices.
3. Reuse the `list_gateway_budgets` result if it is still in the conversation; otherwise call it again before choosing a `name`.
4. For **each** rule: build one manifest (top-level `name`) → `validate_manifest` → `apply_manifest`. `validate_manifest` checks the schema only. The rules in Gotchas are enforced by `apply_manifest`, so check them yourself before applying.

### Manifest Structure

```yaml
name: <unique-rule-name>
type: tenant-budget-config           # or team-budget-config
team_name: <team-name>               # REQUIRED for team-budget-config only
mode: enforce                        # enforce (default) = block on breach; audit = track only; soft_enforce = block only if no other matching budget still has room
limits:                              # one or more of cost_per_day / cost_per_week / cost_per_month / cost_per_quarter, OR cost_per_lifetime alone
  cost_per_day: <n>
applies_to:                          # discriminated by `type`
  type: aggregate                    # aggregate | per-user | per-model | per-virtual-account | per-agent | metadata
  metadata: <key>                    # REQUIRED only when type: metadata (the key to bucket by)
when:                                # optional; omit or use `when: {}` to match everything in scope
  subjects:
    users: { in: [<email>] }         # in / not_in (values are bare, e.g. alice@x.com)
    teams: { in: [<team>] }          # tenant scope only
    virtual_accounts: { in: [<va>] }
    agents: { in: [<agent>] }        # tenant scope only
  models: { in: [<account/model>] }
  provider_accounts: { in: [<account>] }
  virtual_models: { in: [<account/virtual-model>] }   # instead of models/provider_accounts, never both
  metadata:
    <key>: { in: [<value>] }
alerts:
  thresholds: [75, 90, 95, 100]
  notification_target:
    - type: email                    # email | slack-webhook | slack-bot | pagerduty | ms-teams-webhook
      notification_channel: <fqn>
      to_emails: [<email>]           # email needs to_emails; slack-bot needs channels (may be [], names match ^#?[a-z0-9-_]{2,80}$) and optional users: [emails] for DMs
```

**Overrides** (optional, per-entity `applies_to` only) live **inside `applies_to`**, keyed by the entity type — not at the top level:

```yaml
applies_to:
  type: per-user                     # per-model / per-virtual-account / per-agent / metadata analogous
  overrides:
    - users: [<email>]               # per-model → models: [...]; per-virtual-account → virtual_accounts: [...]; per-agent → agents: [...]; metadata → metadata_values: [...]
      limits: { cost_per_day: <n> }  # replaces only the periods it sets; other base periods still apply
```

Each override period must also be in the base `limits`, and an entity may appear in only one override.

Gotchas:
- `applies_to.type` is hyphenated (`per-user`, `per-model`, `per-virtual-account`, `per-agent`) except `aggregate` and `metadata`, and it cannot be changed after the rule is created — to re-partition a budget, create a new rule with a new `name`, then remove the old one with `delete_manifest` `{type, name}` (or set its `mode: audit` to keep tracking). `type`/`team_name` (scope) can't change either. Recreate the budget instead.
- `type: metadata` needs a `metadata: <key>` field.
- `cost_per_lifetime` can't be combined with other periods, whatever the docs say (apply returns 400): a lifetime cap plus a daily cap are two budgets with distinct names, and an existing budget can't switch between lifetime and periodic limits. To make that change, create a new budget.
- `per-user` can't be combined with `when.subjects.virtual_accounts`/`agents`; `per-virtual-account` allows only `virtual_accounts`, and `per-agent` only `agents`, in `when.subjects`.
- `per-model` can't target virtual models (neither `virtual_models` nor a virtual-model id in `models.in`).
- `{{user.email}}` in `to_emails`/`users` is allowed only for `per-user` budgets. If `alerts` is set, it needs at least one `notification_target`. There is no `send_to` field on alerts.
- Usage counts from rule creation, not from the start of the current period, so earlier spend is never backfilled.
- For metadata keys you don't know, discover them from live data (see `observability.md`) — don't ask the user.

## Checklist

- [ ] Did I read existing rules with `list_gateway_budgets` (not `get_gateway_config`)?
- [ ] One rule per manifest, each with a unique `name` not already in the list?
- [ ] Does `when` use the nested `in`/`not_in` form (with `virtual_accounts`, not `virtualaccounts`)?
- [ ] Is `applies_to.type` one of `aggregate`/`per-user`/`per-model`/`per-virtual-account`/`per-agent`/`metadata` (and `metadata:` set for the metadata type), and compatible with `when.subjects`?
- [ ] Lifetime and periodic limits not mixed; override periods a subset of the base?
- [ ] For team scope, is `team_name` set and confirmed to exist?
- [ ] Validated before applying, and checked existing rules for overlap?

## Migrating from V1

V1 is a single tenant-wide config with an ordered `rules[]`; V2 is one manifest per rule. Migrate every V1 rule to a **`tenant-budget-config`** (V1 was always tenant-scoped).

1. In one batch: fetch V1 with `get_gateway_config` (`type: gateway-budget-config`) — the one place `get_gateway_config` still applies — and call `list_gateway_budgets` to see what has already been migrated.
2. Recreate each `rules[]` entry as its own `tenant-budget-config` manifest:
   - `id` → `name`. V2 `name` must be unique across all tenant and team budgets. If `list_gateway_budgets` already shows that name, pick a new one.
   - `audit_mode: false/true` → `mode: enforce/audit`
   - `budget_applies_per: ['user'|'model'|'virtualaccount']` → `applies_to.type: per-user`/`per-model`/`per-virtual-account`; `['metadata.<key>']` → `applies_to: { type: metadata, metadata: <key> }`; omitted → `applies_to: { type: aggregate }`
   - `limit_to` + `unit: cost_per_*` → `limits: { <unit>: <limit_to> }`. `unit: tokens_per_*` has no V2 equivalent: tell the user and skip that rule.
   - flat `when` (`['user:a@x','team:eng']`) → nested `in`/`not_in` (`subjects.users.in: [a@x]`, `subjects.teams.in: [eng]`); `virtualaccount:x` → `subjects.virtual_accounts.in: [x]`; `models: [a]` → `models: { in: [a] }`; `metadata: { k: v }` → `metadata: { k: { in: [v] } }`
   - `alerts` carry over unchanged
3. V2 has no ordering — if a V1 rule was an override above a default, exclude that group from the default with `not_in` (or use per-entity `overrides` inside `applies_to`); otherwise both limits apply and the tightest wins.
4. Create V2 rules in `mode: audit`, verify for a full period, switch to `enforce`, then remove the migrated V1 rules (see 'Disabling V1 rules' in budget-limiting.md). Both run in parallel during the transition.
