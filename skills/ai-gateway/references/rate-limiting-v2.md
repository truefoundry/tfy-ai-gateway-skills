---
name: rate-limiting-v2
description: Rate Limiting V2 — named, independent rate limits on LLM requests/tokens (`tenant-rate-limit-config/model`) and MCP tool calls (`tenant-rate-limit-config/mcp`). Read for any new rate limit, any change to a V2 limit, and any "what rate limits do we have" question.
---

# Rate Limiting V2

V2 is the default for every new rate limit. V1 (`gateway-rate-limiting-config`) is deprecated; read `rate-limiting.md` only to read, disable or migrate existing V1 rules.

**The tools cannot write V2 limits today.** `get_manifest_json_schema`, `validate_manifest`, `apply_manifest` and `delete_manifest` reject `tenant-rate-limit-config/*` (the platform resolves the type without its `/model` or `/mcp` suffix and finds nothing), and no tool lists V2 limits. Don't try them. You build the YAML; the user applies it in the UI.

## How V2 behaves

- **One limit = one manifest**, identified by `name`. Model and MCP limits are separate families and may share a name.
- **No ordering, all must pass.** Every limit whose `when` matches is checked, usage counts against each one, and the request is blocked if any matching `enforce` limit is breached. To exempt a group from a broad default, use `not_in`.
- **V1 runs first.** If a V1 rule blocks, V2 is not consulted. Both count traffic they match, so a V1 rule and a V2 limit with the same intent cap the request twice.
- Tenant-scoped only (tenant admins), no team scope, no alerts.

## Inputs to collect

Ask with `ask_user_question` for anything the user didn't say and that has more than one valid answer.

1. **Family** — LLM traffic → `tenant-rate-limit-config/model`; MCP tool calls → `tenant-rate-limit-config/mcp`.
2. **Who/what it applies to** → `when` (see the target table below). Omit `when` to match all tenant traffic.
3. **Limits** — one or more windows; all are enforced together. Positive integers.
4. **Bucketing** → `applies_to.type`: one shared pool (`aggregate`) or one counter per entity.
5. **Mode** — default `enforce`. Suggest `audit` when the user wants to size a limit before blocking.
6. **Name** — new and unique within the family: starts with a letter, then letters, digits or hyphens, ends with a letter or digit, 2–62 characters.

### Resolving the target (`when`)

| User mentions | `when` field (values are bare, no `user:`/`team:` prefix) |
|---|---|
| a user / email | `subjects.users.in: [alice@example.com]` |
| a team | `subjects.teams.in: [ml-team]` |
| a virtual account | `subjects.virtual_accounts.in: [ci-bot]` |
| an agent | `subjects.agents.in: [<agent>]` |
| a model | `models.in: [<providerAccount>/<model>]` (model only) |
| a provider account | `provider_accounts.in: [openai-main]` (model only) |
| an MCP server or one tool | `mcp_servers.in: [search]` or `[search:web_lookup]` (MCP only) |
| a metadata term (tenant, app, project…) | `metadata: { <key>: { in: [<value>] } }` |

- Each filter takes `in` and/or `not_in`; `*` is a wildcard. Different filters are ANDed. Among subject kinds, an `in` match on any one is enough, and any `not_in` match excludes the caller.
- A metadata term that isn't a user, team or VA is a metadata key. Don't ask the user for the key name: discover it from live data (see `observability.md`, `gateway_model_metrics`).
- Model family only: `virtual_models` / `virtual_provider_accounts` filters exist but can't be combined with `models` / `provider_accounts` (400). A virtual-model id can also go in `models.in`.

### Bucketing (`applies_to`)

| Model family | MCP family | Effect |
|---|---|---|
| `aggregate` | `aggregate` | one shared counter |
| `per-user` | `per-user` | one counter per user |
| `per-model` | `per-mcp` | one per model / per MCP server |
| `per-virtual-account` | `per-virtual-account` | one per VA |
| `metadata` + `metadata: <key>` | same | one per distinct value of that key |

There is no per-agent partition. These combinations are rejected with 400 at apply time, so check them yourself:
- `per-user` with `when.subjects.virtual_accounts` or `agents`.
- `per-virtual-account` with `when.subjects.users`, `teams` or `agents`.
- `per-model` with a virtual-model id in `when.models.in` or in an override.

**Overrides** (per-entity types only) give named entities different limits. Each override may set only periods that the base `limits` already sets, it replaces only those periods, and an entity may appear in only one override (400 otherwise). Target keys: `users`, `models`, `mcps`, `virtual_accounts`, `metadata_values`.

## Steps

1. **Session context** — `controlPlaneUrl` is in your instructions; call `get_session_context` only if it is missing.
2. **Existing limits** — V2 limits can't be read with tools, and `get_gateway_config` returns nothing for them. For "what rate limits exist", call `get_gateway_config` with `type: gateway-rate-limiting-config`, report any V1 rules, and say that V2 limits are visible only at `{controlPlaneUrl}/llm-gateway/policies/rate-limiting-v2`. Never answer "no rate limits" from V1 alone.
   This call and any metadata-key discovery query are independent: issue them in one batch.
3. **Build the YAML** from the template below. Include only the fields you need; `mode` and `log_request_body_on_block` have defaults (`enforce`, `false`) but writing them out makes the intent clear to the user.
4. **Hand off.** Show the YAML in a code block and tell the user:
   - New limit: open `{controlPlaneUrl}/llm-gateway/policies/rate-limiting-v2` → **+ Add Rule** → choose **Model** or **MCP** → in the **Configure** step click **Apply as YAML** → paste and apply.
   - Change or delete an existing limit: open it from its row on the same page. Ask the user to paste its current YAML first so you change only what was asked; saving a manifest with an existing `name` replaces that limit.
   - Use the real `controlPlaneUrl`, never a placeholder.
5. **Don't claim it was applied.** Say what the user needs to do, and offer to check behavior afterwards: a blocked request carries `x-tfy-applied-rules` naming the limit, and an `audit` limit shows `"audit_mode":true` there.

Rules that hold on edit:
- `applies_to.type` (and the `metadata` key) can't change after creation (403). To re-partition, create a new limit with a new name and delete the old one.
- A new limit counts from zero; it never inherits V1 usage.

## Manifest template

```yaml
type: tenant-rate-limit-config/model      # or tenant-rate-limit-config/mcp
name: <unique-name>
when:                                     # optional; omit to match all tenant traffic
  subjects:
    users: { in: [<email>] }              # in / not_in, "*" wildcard
    teams: { in: [<team>] }
    virtual_accounts: { not_in: [<va>] }
    agents: { in: [<agent>] }
  models: { in: [<account/model>] }       # model only
  provider_accounts: { in: [<account>] }  # model only
  # mcp_servers: { in: [<server> or <server:tool>] }   # MCP only, instead of models/provider_accounts
  metadata:
    <key>: { in: [<value>] }
limits:                                   # one or more, positive integers
  requests_per_minute: <n>                # model: requests_/tokens_per_minute|hour|day
  # tool_calls_per_minute: <n>            # MCP: tool_calls_per_minute|hour|day
applies_to:
  type: aggregate                         # see the bucketing table
  # metadata: <key>                       # required when type: metadata
  # overrides:                            # per-entity types only
  #   - users: [<email>]                  # or models / mcps / virtual_accounts / metadata_values
  #     limits: { requests_per_minute: <n> }
mode: enforce                             # enforce | audit (track only) | soft_enforce (block only if no other matching limit has room)
log_request_body_on_block: false          # true keeps the request body on the trace of blocked requests
```

Example — 100 requests per minute shared by team `ml-team` across all models:

```yaml
type: tenant-rate-limit-config/model
name: ml-team-rpm
when:
  subjects:
    teams: { in: [ml-team] }
limits:
  requests_per_minute: 100
applies_to:
  type: aggregate
mode: enforce
log_request_body_on_block: false
```

## Checklist

- [ ] Right family (`/model` for LLM traffic, `/mcp` for tool calls) and limit keys from that family?
- [ ] New unique `name` matching the name pattern?
- [ ] `when` uses the nested `in`/`not_in` form with bare values?
- [ ] `applies_to.type` compatible with the subject filters, and overrides only reuse base periods?
- [ ] Did not call `get_manifest_json_schema` / `validate_manifest` / `apply_manifest` / `delete_manifest` for this type?
- [ ] Showed the YAML and the real `{controlPlaneUrl}/llm-gateway/policies/rate-limiting-v2` link with the **+ Add Rule** → **Apply as YAML** steps?

For worked examples (per-project metadata limits, MCP tool carve-outs, soft-enforce backstops): `get_page_layout` on https://www.truefoundry.com/docs/ai-gateway/ratelimiting-v2, then `get_section_content` for "Practical examples".
