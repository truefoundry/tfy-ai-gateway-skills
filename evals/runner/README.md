# Experiment runner

Runs the Ask TFY eval cases on devtest against one skills commit, grades every answer claim by
claim, and records the result as a LangSmith experiment and a local run directory. `gate` then
says whether a candidate commit made anything worse than a baseline.

```text
python -m runner run --skills-ref <commit>
  resolve the ref to a full SHA on origin; read evals/evals.json at that SHA
  (skills/evals/evals.json on older commits); cases with `skip` are reported, not run
  refuse to start with uncommitted runner or harness changes (--allow-dirty for throwaway runs)
  probe: create one Ask TFY session with x-ask-tfy-skills-ref, check sfy stamped that SHA
  LangSmith evaluate(), dataset ask-tfy-core, each case --repeats times (default 3)
    target     tfy_eval run_question, through sfy, writes denied unless writes-allowed.txt;
               every session checked for the same skills commit and model, else the run aborts
    evaluators tfy_eval judge (claim by claim, with tool results) + code checks
  runs/<time>-<sha>/  config, answers, grades, transcripts, summary.json, report.md
```

`runner/` is the experiment runner; `tfy_eval/` is the harness it drives (agent turns, the judge,
reports). Neither is under `skills/`, so neither reaches the agent's sandbox.

## How Ask TFY is reached

Through servicefoundry-server, exactly as the product UI does: sfy builds the agent (instructions,
MCP servers, skills, the caller's session context) and the runner only chooses the skills commit,
with the `x-ask-tfy-skills-ref` header. sfy honours it only with
`ASK_TFY_ALLOW_SKILLS_REF_OVERRIDE` on, which is devtest only.

Every session is checked against the SHA and the model sfy stamped on it. A session on any other
commit or model aborts the whole run: no `summary.json` is written and the gate refuses the
directory, so a run can never score a commit or model it did not test. The commit must be on a
branch of `origin`, or the sandbox cannot fetch it.

sfy picks the model from the tenant's AI settings, falling back to `AI_FEATURES_MODEL`. On devtest
that is DeepSeek V4 Flash, while production runs Sonnet 5.5; the model is recorded on every run and
two runs on different models are never compared.

The judge does not go through sfy: it runs as its own TrueForge session (`TRUEFORGE_BASE_URL`).

## Setup

```bash
cd evals
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp runner/.env.example runner/.env      # gitignored; fill in the blanks
set -a && source runner/.env && set +a
.venv/bin/python -m runner.selftest     # offline; also: python -m tfy_eval.selftest
```

| Variable | What it is |
|---|---|
| `ASK_TFY_HOST` | Devtest control plane URL |
| `ASK_TFY_TENANT` | Tenant the PAT belongs to |
| `TFY_API_KEY` | Devtest PAT. Ask TFY runs as this user, and every case lands in their Ask TFY history |
| `TRUEFORGE_BASE_URL` | Judge: the devtest TrueForge URL, ending in `/trueforge` |
| `TRUEFORGE_JUDGE_MODEL` | Judge model, e.g. `tfy-ai-anthropic/claude-sonnet-5-5` |
| `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT` | The `ask-tfy` workspace |
| `EVAL_FIXTURE_MANAGER` | Email of the manager of the `eval-` fixture teams (`seed_fixtures` only) |

## Use

```bash
python -m runner.seed_fixtures                                       # the eval- entities cases name
python -m runner probe --skills-ref origin/platform                  # pin check only: one session, no turn
python -m runner run --skills-ref origin/platform --only s1           # one case, to check the setup
python -m runner ab --baseline-ref origin/platform --skills-ref origin/my-fix-branch   # both sides now
python -m runner affected --baseline runs/<nightly> --skills-ref origin/my-fix-branch  # what a PR runs
python -m runner gate --baseline runs/<base> [runs/<base2>] --candidate runs/<cand> [runs/<cand2>]
```

`ab` runs both commits at the same time, so they see the same devtest data and deployments, then
gates. A baseline from last week is confounded by everything that changed on devtest since.

A full run is about 220 trials: budget one to two hours at `--concurrency 4`. With Claude Haiku
on low reasoning a trial costs about $0.03 to $0.04, about $8 a night; the report adds what the
judge cost. Use `--only` while iterating. `--kind` (`nightly`, `pr-<number>`, default `local`)
goes into the experiment name, `ask-tfy <kind> <sha>`, so LangSmith can tell runs apart.

## In CI

- `eval-nightly.yml` seeds fixtures and runs every case on `platform` at 02:00 IST. GitHub only
  schedules workflows from the default branch, so it also lives on `develop`. The run
  directory is the artifact `ask-tfy-baseline`, encrypted because the repo is public and runs hold
  devtest data: `openssl enc -d -aes-256-cbc -pbkdf2 -pass env:EVAL_ARTIFACT_KEY -in baseline.tar.gz.enc | tar -xz`.
  Job summaries show only the headline numbers; the redacted traces are in LangSmith. Last, it
  gates the run against the previous successful night (cases changed since are accepted) and
  fails the job on a regression; a runner, judge or model change between nights only warns. With
  an `EVAL_SLACK_WEBHOOK_URL` secret it posts the verdict and headline to Slack.
- `eval-pr.yml` runs on every PR from this repo that touches `skills/`, `evals/` or these
  workflows. `affected` compares the PR with the latest nightly baseline and picks what to run;
  `all` and `ab` cost $8 to $15, so they wait for a maintainer to add the `eval` label:

  | Mode | When | Runs |
  |---|---|---|
  | `none` | No change under `skills/` or to the cases | Nothing |
  | `cases` | Reference files or cases changed | Cases whose baseline trials read a changed file, plus changed and new cases, gated against the nightly run |
  | `all` | `SKILL.md` changed | Every case, gated against the nightly run |
  | `ab` | Runner or harness changed | Full `ab` against `platform` |
  | `stale` | `platform` has skills, case or runner changes the PR lacks | Nothing: merge `platform` |

  The gate goes to the PR as a comment. A PR that intends to change or remove cases lists them in
  its description as `Eval-Accept: s12,s13`.
- `eval-selftest.yml` runs both selftests on every PR that touches `evals/`.

Comparing with last night's run instead of running both sides saves half the turns, at the cost
of up to a day of devtest drift; fixtures are re-seeded before every run to keep that small.

## Trial outcomes

| Outcome | Examples | Counts as |
|---|---|---|
| Answered | | Judge verdict: passes at score ≥ 0.7, no contradiction, every critical claim supported. A non-critical claim that starts with a condition ("If …", "After …") whose condition never occurred is ruled `not_applicable` and left out of the score, so write branch-specific claims that way |
| Agent failure | Step limit, still waiting on approvals after `--max-rounds`, empty answer, server execution timeout | Fail, whatever it said on the way (not retried) |
| Infrastructure failure | Dropped turn, model error, poll timeout, MCP login needed | Retried up to `--retries` (a timed-out turn is cancelled first), then unmeasured; interim text is never graded |

## What is measured

| Feedback key | Meaning |
|---|---|
| `expectation_score`, `correct` | Judge score and whether it passed |
| `contradictions`, `high_risk_additions` | Confidently wrong statements, including ones the tool results contradict |
| `agent_failure`, `infra_failure` | See trial outcomes |
| `judge_error` | Answered, but the judge failed twice: unmeasured |
| `unapproved_writes` | MCP write tools whose call was never put to approval, or writes from a sandbox program, in any attempt. Should always be 0 |
| `answer_key_reads` | Tool calls that touched `evals.json` (older skills commits ship it in the sandbox). Should always be 0 |
| `writes_denied` | Approval prompts the runner denied |
| `secret_requested` | Asked for a secret through the masked form; the runner refuses it |
| `clarification_asked` | Asked a clarifying question, with ask_user_question or by ending its turn on one (answered with the case's `clarification_reply`; with none scripted, ask_user_question is told the user did not answer) |
| `tool_calls`, `duration_s`, `cost_usd` | Efficiency |
| `judge_cost_usd` | What grading the trial cost |

Outputs and feedback comments are redacted with `runner/redaction.py` before they reach
LangSmith; the judge and the local run directory see them unredacted.

## The gate

Each side is one or more complete runs of one commit, pooled. It fails on:

- a significant drop across all compared cases (paired sign-flip test). With 3 trials a side
  this is what carries the gate;
- a case whose pass rate dropped significantly (one-sided Fisher exact test, Holm-corrected across
  the compared cases at 0.05). Without the correction, chance alone would fail half of unchanged
  75-case runs; with it, no single case can reach significance on 3 trials a side. Drops like
  3/3 to 0/3 or 1/3 are listed under "watch", and pooling more runs of each side settles them;
- runs that are not comparable: different agent model, judge model or judge version (a hash of
  the judge code), runner or harness code, tenant, write allowlist or scoring settings;
- a case that changed or was removed, unless passed with `--accept s12,s13`: a PR must not be
  able to weaken or delete the case it fails;
- more than 10% unmeasured trials on either side (missing trials count), or a case measured on
  the baseline but mostly unmeasured on the candidate, since skills can cause "infrastructure"
  failures too;
- any write in the candidate that was never put to approval;
- any trial, on either side, that read `evals.json`.

A candidate may run only some cases (`--only`); the others are listed as not run, not removed.
It may not skip a case that changed or is new: the gate refuses that run.

`ab` probes both commits, picks the judge and syncs the dataset before either side runs a turn,
and stops the other side as soon as one fails.

## Not built yet

- Model choice: sfy has no per-session model override, so devtest runs measure DeepSeek V4 Flash.
- Fresh traces per run for the trace and metrics cases, and eval-owned deployments for the AI
  Engineering cases. Cases whose data expired carry `skip` until then.
- The `ask-tfy-regressions` dataset from Engine issues.
