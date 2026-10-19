# askbench: does a skills change make Ask TFY better or worse?

Ask TFY, the in-product assistant, mounts this repo's `skills/` directory. askbench runs a fixed set of
troubleshooting questions through Ask TFY twice, once with the skills at a base git ref and once at a head
ref, and tells you whether head answers fewer of them correctly. It lives outside `skills/` on purpose, so
Ask TFY can never read the answers. The answers are public like everything else here: the check detects
regressions, it does not stop a change from being written to the test.

## What it measures

- 22 troubleshooting questions (`cases.json`: `id`, `area`, `kind`, `ask`), each phrased the way a user would
  write it, with neutral object names.
- `answers.json` holds, per question, the facts a correct answer must state (`must_include`) and the wrong
  claims it must not make (`must_not`). Every fact was observed on a live TrueFoundry tenant (verified
  2026-10-17), not copied from the docs; a fact states only what was observed.
- Each question gets a fresh Ask TFY session with the live agent definition, and only two inputs changed: the
  skills git url/ref and, optionally, the model. The benchmark answers every write approval with a denial and
  records it. That protects only if the live agent asks before writing, so use a read-only token (below).

Two scores per question:

| Score | How | Role |
|---|---|---|
| Verified | A model (`--judge-model`) marks each fact and wrong claim through the TrueFoundry gateway and must quote a span of Ask TFY's reply. Code then accepts the item only if the span is 5-40 words, is a normalised substring of the reply, and either shares a content word with the fact (or wrong-claim) text or matches one of its regexes in `answers.json`. | headline |
| Code | The regexes in `answers.json` over the whole reply. Facts with no regex are left out. | cross-check |

What the span check guarantees: a verified hit is backed by text the reply really contains, of bounded
length, that is about the fact. A same-family judge therefore cannot pass a fact with invented text, with the
whole reply, or with an unrelated sentence. What it does not guarantee: that the quoted sentence asserts the
fact rather than denying it, or that the judge reads it the way a human would. That residual judgement is why
the regex score is printed next to it; a large gap between the two means look at the spans. A question is
solved when every fact is stated, no wrong claim is made, and the run ended normally.

## Run it locally

Zero npm dependencies, Node >= 20.

```bash
export ASKBENCH_TFY_HOST=https://<your tenant host>
export ASKBENCH_TFY_API_KEY=<token allowed to create Ask TFY sessions>

node evals/askbench/run.mjs --ref platform --out out/base
node evals/askbench/run.mjs --ref my-branch --repo https://github.com/<you>/tfy-ai-gateway-skills --out out/head
node evals/askbench/compare.mjs --base out/base --head out/head
```

`run.mjs` options: `--ref` (required), `--out` (required), `--repo` (skills git url, default this repo),
`--model` and `--judge-model` (default `tfy-ai-anthropic/claude-sonnet-5-5`), `--only R01,R02`,
`--concurrency` (default 1), `--max-usd N`, `--max-minutes N`, `--no-verify`, `--rerun`, `--redo-only`. A case
already in `--out` is skipped, so an interrupted run resumes; harness errors and failed verifications are
redone, and `--redo-only` does only that (CI uses it as a second pass).

- The run **aborts on the first gateway "Budget exceeded" 429** (exit 3). It stops starting cases once spend
  reaches `--max-usd` (counting what `--out` already holds) or after `--max-minutes` (exit 0; `run.json` lists
  what was not run). Spend is read from the cost Ask TFY reports per turn and excludes the verifier; a case
  that reports no cost prints a warning, since the cap cannot see it. The gateway budget is the real backstop.
- `compare.mjs` exits **1** if head's solved count is below base's by more than `--max-drop` (default 2), if
  head makes a `must_not` claim that base did not make on the same case, or if fewer than `--min-coverage`
  (default 1.0, every case) of the cases are comparable. A case is comparable only when both arms have it
  without a harness error and, when verifying, with a verifier result; the rest are listed and are never
  counted as passes. It exits **2** on bad arguments, nothing comparable, or arms that ran with a different
  model or judge. It writes the table to stdout and to `$GITHUB_STEP_SUMMARY` when set. If no record has a
  verifier result it falls back to the code score and says so.
- `publish.mjs --in <dir> --out <dir>` writes the upload-safe form (see CI).
- Tests, offline: `node --test evals/askbench/askbench.test.mjs`.
- Optional: `ASKBENCH_TFY_TENANT` (default `truefoundry`) and `ASKBENCH_MCP_EXTRA`, a JSON object
  `{"<server name>": {"url": "...", "description": "..."}}` for any MCP server your tenant's live agent lists
  beyond the platform and docs servers; the run stops with a clear error if one is missing.

## In CI

`.github/workflows/askbench.yml` runs the unit tests (no secrets), then base then head, then compare. It
starts on `workflow_dispatch` (inputs `base_ref`, `head_ref`, `max_usd`) or on a pull request carrying the
**`askbench`** label (when labelled and on each push while labelled), never on every PR. For a PR, base is the
PR's base branch here and head is the PR's head ref on the head repository; the workflow prints both commit
shas and fails if either ref moved during the run. Each arm gets half of `max_usd`.

Setup, once:

- Use an **empty sandbox tenant** and a **read-only token**. Ask TFY's tools run with that token, and the
  benchmark's denial of writes only works if the agent asks first.
- Create a GitHub Environment named `askbench` with required reviewers, and put the secrets in it:
  `ASKBENCH_TFY_HOST`, `ASKBENCH_TFY_API_KEY`, optionally `ASKBENCH_MCP_EXTRA` (and the variable
  `ASKBENCH_TFY_TENANT`). Anyone who can label a PR can otherwise start a ~$270 run. Keep the repository
  setting "send secrets to workflows from fork PRs" off.
- Without the secrets a same-repo run writes a "not run" summary and succeeds. A pull request from a fork
  cannot get secrets, so its job **fails** with an explanation; a maintainer runs it with `workflow_dispatch`.

The artifact (`askbench-results`, kept 7 days, public to anyone who can read the repository) is built by
`publish.mjs`: per-case scores, verdicts with their spans (at most 40 words each), tool names, latency and
cost. It holds no reply text and no questions, and the control-plane host, keys, bearer tokens and email
addresses are scrubbed. The full records stay on the runner.

## Cost and noise

- About $6 per question per arm, so about $130 per arm and $270 for a full base-vs-head run, plus a small
  verifier cost. Use `--only` for a quick look, and set `--max-usd`.
- Single runs are noisy: expect about 2-3 of 22 questions to flip between identical runs. That is why
  `--max-drop` defaults to 2. A real change shows up as a lost case with the same facts missing on a re-run.

## Reading the table

One row per case: `yes`/`no` is solved for base and head, then facts hit and wrong claims for each, and
`fixed` or `lost` where the two differ. The totals table has the headline (verified solved), the regex
cross-check, facts hit, wrong claims, p50 latency and cost. Above the table: the two skills refs and models,
warnings about runs that stopped or aborted, the cases that could not be compared, and any regression with
its reason. A big gap between verified and code solved means a regex is too narrow or too loose, or a judge
mistake; check the case's `verified` block in the run's JSON, where each hit carries its span.

## Add a case

1. Reproduce the behaviour on a live tenant first. A case that was not observed does not go in.
2. Add `{id, area, kind, ask}` to `cases.json`: a self-contained user question with neutral names
   (`my-va`, `my-mcp`), no secrets, no hint of the answer.
3. Add `{id, verdict, must_include, must_not}` to `answers.json`. Each `must_include` entry is
   `{fact, match}`: `fact` states only what was observed, in one sentence; `match` is a list of case-insensitive
   regexes that catch common phrasings (they also let a verifier span that shares no word with the fact still
   count). `must_not` lists confident wrong answers a user could be given, such as "calls it a bug". No `match`
   may match its own ask (the tests check this).
4. Run `node --test evals/askbench/askbench.test.mjs`, then a base run on the case to see it behave.
