# Eval fixtures

The cases run on the devtest tenant and name these entities. They are seeded by
`runner/seed_fixtures.py` in ask-tfy-quality; change both together.

| Entity | State | Cases |
|---|---|---|
| Team `eval-engineering` | No members; `provider-account-access` on `openai-main` | s27, s47 |
| Team `eval-platform` | No members, no access | s45 |
| Team `eval-budget` | Team budget `eval-budget-monthly`: audit mode, $100 per month, aggregate | s25 |
| User `test@example.com` | `provider-account-access` on `openai-main`; in no `eval-` team | s27, s46 |

Skipped trace cases (s65-s73) name `eval-` models, rules and virtual models that do not exist yet;
they run once traces are seeded for them.
