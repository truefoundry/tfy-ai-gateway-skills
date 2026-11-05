# Eval fixtures

The cases run on the devtest tenant and name these entities. They are seeded by
`runner/seed_fixtures.py` before every run; change both together.

| Entity | State | Cases |
|---|---|---|
| Team `eval-engineering` | No members; `provider-account-access` on `openai-main` | s27, s47 |
| Team `eval-platform` | No members, no access | s45 |
| Team `eval-budget` | Team budget `eval-budget-monthly`: audit mode, $100 per month, aggregate | s25 |
| User `test@example.com` | `provider-account-access` on `openai-main`; in no `eval-` team | s27, s46 |
| User `eval-carol@example.com` | Tenant role `read-only-member` (plus the default `member`) | s58 |
| Provider account `eval-openai` | OpenAI with an invalid API key; model `primary` always fails with 401 | s68, s73 |
| Provider account `eval-vm` | Virtual models `chat`, `budget`, `rate-limit` routed to `tfy-ai-openrouter/openai-gpt-5.4-nano`; `fallback` tries `eval-openai/primary` first | s65-s73 |
| Budget `eval-budget-enforce` | Tenant budget, enforce, $0.000001 per day, on `eval-vm/budget` only | s67 |
| Rate limit `eval-rate-limit` | 1 request per minute, enforce, on `eval-vm/rate-limit` only | s69 |

The token's own subject (the `ask-ai-eval` virtual account in CI) gets `provider-account-access` on
both eval- accounts. Every limit is scoped to an eval- model, so no one else's traffic is affected.

## Traces

Traces expire, so the trace cases name `{{trace.<name>.<field>}}` placeholders instead of ids. The
seeder sends one request per trace, waits until the trace is queryable and has the span error below,
and writes `id`, `time`, `epoch_ms`, `sender` and `error` for each to `runner/runs/fixtures.json`.
The runner fills them in for the agent and the judge, and refuses a case whose values are missing or
more than two days old.

| Trace | Request | Span error | Cases |
|---|---|---|---|
| `not_found` | `eval-openai/o4-mini`, which does not exist | `tfy-model-not-found` (403) | s68 |
| `provider_400` | `eval-vm/chat` with `top_logprobs: 50` (the provider allows 20) | `request-failure-400` | s65, s71 |
| `guardrail` | `eval-vm/chat` with PII, `X-TFY-GUARDRAILS` input guardrail `tfy-guardrail/pii` | `tfy-input-guardrail` (400) | s66 |
| `budget` | `eval-vm/budget` until the budget blocks | `tfy-budget-limit` (429) | s67 |
| `rate_limit` | `eval-vm/rate-limit` until the limit blocks | `tfy-rate-limit` (429) | s69 |
| `fallback` | `eval-vm/fallback`: `eval-openai/primary` fails, the fallback answers | `request-failure-401`, request 200 | s73 |

Still skipped: s70 (needs an eval- MCP server and MCP traffic) and s75 (needs a caller that cannot
manage the provider account; the eval token can manage all of them).
