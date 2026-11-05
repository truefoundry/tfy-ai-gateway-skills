// run.mjs — runs the benchmark questions against Ask TFY with the skills mount pointed at one git ref.
//
//   node evals/askbench/run.mjs --ref <skills git ref> --out <dir> [--repo <git url>]
//        [--model tfy-ai-anthropic/claude-sonnet-5-5] [--judge-model <same default>] [--only R01,R02]
//        [--concurrency 1] [--max-usd N] [--max-minutes N] [--no-verify] [--rerun]
//
// Env: ASKBENCH_TFY_HOST, ASKBENCH_TFY_API_KEY (a token allowed to create Ask TFY sessions);
// optional ASKBENCH_TFY_TENANT, ASKBENCH_MCP_EXTRA (JSON, MCP servers an install's live spec adds).
//
// One JSON per case in <dir> (redacted), plus run.json. A case already on disk is skipped unless it hit a
// harness error, so a run is resumable (a second pass on the same --out redoes errors and failed verifications).
// The whole run aborts on the first gateway "Budget exceeded" (exit 3); it stops starting cases once spend
// (counting what is already in --out) reaches --max-usd, or after --max-minutes (exit 0, run.json says so).
// Writes are always denied.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { env, redact, secretsOf } from './harness/env.mjs';
import { makeClient, isBudgetExceeded } from './harness/client.mjs';
import { buildDirect, UPSTREAM_SKILLS } from './harness/direct.mjs';
import { verifyCase } from './harness/verify.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
export const CASES = join(HERE, 'cases.json');
export const ANSWERS = join(HERE, 'answers.json');
export const DEFAULT_MODEL = 'tfy-ai-anthropic/claude-sonnet-5-5';

export const USAGE = `usage: node evals/askbench/run.mjs --ref <skills git ref> --out <dir> [options]
  --ref <ref>           git ref of the skills repo Ask TFY mounts (branch or tag)           (required)
  --out <dir>           where one <id>.json per case and run.json are written               (required)
  --repo <url>          skills git url (default ${UPSTREAM_SKILLS.url})
  --model <id>          Ask TFY's model, <provider-account>/<model> (default ${DEFAULT_MODEL})
  --judge-model <id>    verifier model (default ${DEFAULT_MODEL})
  --only R01,R02        run only these case ids
  --concurrency <n>     cases in flight (default 1)
  --max-usd <n>         stop starting cases once this much Ask TFY spend is reached (counts what --out holds)
  --max-minutes <n>     stop starting cases after this much wall clock
  --no-verify           skip the verifier (code score only)
  --redo-only           only redo cases already in --out that hit a harness error or a failed verification
  --rerun               re-run cases already on disk
env: ASKBENCH_TFY_HOST, ASKBENCH_TFY_API_KEY; optional ASKBENCH_TFY_TENANT, ASKBENCH_MCP_EXTRA`;

const harnessError = (user, e) => ({ user, status: 'harness_error', error: e.message, text: '', ms: 0, cost_usd: 0, tokens: 0, tool_calls: [], tool_errors: [], approvals: [] });

/** Runs one case: a fresh session, then the ask. */
export async function runCase(client, c) {
  let session;
  try { session = await client.createSession(); } catch (e) {
    return { id: c.id, model: null, messages: [harnessError(c.ask, e)] };
  }
  const messages = [];
  try {
    messages.push({ user: c.ask, ...(await client.ask(session.id, c.ask)) });
  } catch (e) {
    messages.push(harnessError(c.ask, e));
  }
  return { id: c.id, model: session.agent?.spec?.model?.name ?? null, messages };
}

export const budgetHit = rec => (rec.messages ?? []).some(m => m.status !== 'done' && isBudgetExceeded(m.error));
export const costOf = rec => (rec.messages ?? []).reduce((s, m) => s + (m.cost_usd ?? 0), 0);

const readJson = p => JSON.parse(readFileSync(p, 'utf8'));

/**
 * The run loop, with the client and verifier injected. Returns
 * {ran, resumed, spent, aborted: null|'budget', stopped: null|'max-usd', not_run: [ids]}.
 */
export async function runAll({ cases, answers, out, client, concurrency = 1, maxUsd = null, maxMinutes = null, verifier = null, secrets = [], rerun = false, log = () => {}, now = Date.now }) {
  mkdirSync(out, { recursive: true });
  const gold = Object.fromEntries(answers.map(a => [a.id, a]));
  const path = id => join(out, `${id}.json`);
  const state = { ran: 0, resumed: 0, spent: 0, aborted: null, stopped: null, not_run: [] };
  const write = rec => writeFileSync(path(rec.id), JSON.stringify(redact(rec, secrets), null, 1));
  const t0 = now();
  const needsAsk = id => {
    if (rerun || !existsSync(path(id))) return true;
    return readJson(path(id)).messages.some(m => m.status === 'harness_error' || (m.status === 'done' && !m.text?.trim()));
  };
  // Spend already on disk counts toward the cap, so a second pass cannot spend the cap again.
  for (const c of cases) if (!needsAsk(c.id)) state.spent += costOf(readJson(path(c.id)));

  const verify = async rec => {
    if (!verifier || !gold[rec.id] || rec.messages.some(m => m.status === 'harness_error')) return;
    try { rec.verified = await verifier(gold[rec.id], rec); } catch (e) {
      rec.verified = { error: e.message.slice(0, 300) };
      if (isBudgetExceeded(e.message)) state.aborted ??= 'budget';
    }
  };

  let i = 0;
  await Promise.all(Array.from({ length: Math.min(concurrency, cases.length) }, async () => {
    while (i < cases.length) {
      const c = cases[i++];
      if (state.aborted) { state.not_run.push(c.id); continue; }
      if (maxUsd != null && state.spent >= maxUsd) { state.stopped = 'max-usd'; state.not_run.push(c.id); continue; }
      if (maxMinutes != null && (now() - t0) / 60000 >= maxMinutes) { state.stopped = 'max-minutes'; state.not_run.push(c.id); continue; }
      let rec;
      if (needsAsk(c.id)) {
        rec = { ...(await runCase(client, c)), area: c.area, kind: c.kind };
        state.ran++;
        state.spent += costOf(rec);
        if (budgetHit(rec)) state.aborted ??= 'budget';
      } else {
        rec = readJson(path(c.id));
        if (!verifier || (rec.verified && !rec.verified.error)) { state.resumed++; continue; }
        delete rec.verified; // only the verifier is re-run on a settled case
        state.resumed++;
      }
      await verify(rec);
      write(rec);
      const m = rec.messages;
      log(`${c.id} ${m.map(x => x.status).join('>')} ${Math.round(m.reduce((a, x) => a + x.ms, 0) / 1000)}s $${costOf(rec).toFixed(2)} tools ${m.reduce((a, x) => a + x.tool_calls.length, 0)}${rec.verified ? (rec.verified.error ? ' verify-failed' : ` verified ${rec.verified.solved ? 'solved' : 'unsolved'}`) : ''}${m.some(x => x.status === 'done' && !x.cost_usd) ? ' WARNING: no cost reported, --max-usd cannot see this case' : ''}`);
    }
  }));
  state.not_run = state.not_run.filter(id => !existsSync(path(id))).sort();
  return state;
}

function parseArgs(argv) {
  const flags = new Set(['--no-verify', '--rerun', '--redo-only', '--help', '-h']);
  const o = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('-')) throw new Error(`unexpected argument ${a}`);
    if (flags.has(a)) { o[a] = true; continue; }
    if (argv[i + 1] === undefined || argv[i + 1].startsWith('--')) throw new Error(`${a} needs a value`);
    o[a] = argv[++i];
  }
  return o;
}

export async function main(argv, { fetch: f = fetch, envVars = process.env, pollMs = 5000 } = {}) {
  const a = parseArgs(argv);
  if (a['--help'] || a['-h']) { console.log(USAGE); return 0; }
  if (!a['--ref'] || !a['--out']) throw new Error(`--ref and --out are required\n${USAGE}`);
  const { origin, key, tenant } = env(envVars);
  const model = a['--model'] ?? DEFAULT_MODEL;
  const judgeModel = a['--judge-model'] ?? DEFAULT_MODEL;
  const only = a['--only']?.split(',');
  const maxUsd = a['--max-usd'] != null ? Number(a['--max-usd']) : null;
  if (maxUsd != null && !(maxUsd >= 0)) throw new Error('--max-usd must be a number');
  const maxMinutes = a['--max-minutes'] != null ? Number(a['--max-minutes']) : null;
  if (maxMinutes != null && !(maxMinutes > 0)) throw new Error('--max-minutes must be a positive number');
  const selected = readJson(CASES).filter(c => !only || only.includes(c.id));
  if (only && selected.length !== only.length) throw new Error(`unknown case id in --only: ${only.filter(id => !selected.some(c => c.id === id)).join(', ')}`);
  const redoOnly = !!a['--redo-only'];
  const cases = redoOnly ? selected.filter(c => existsSync(join(a['--out'], `${c.id}.json`))) : selected;
  let extraMcp = {};
  if (envVars.ASKBENCH_MCP_EXTRA) { try { extraMcp = JSON.parse(envVars.ASKBENCH_MCP_EXTRA); } catch { throw new Error('ASKBENCH_MCP_EXTRA is not valid JSON'); } }

  // The template is a fresh platform-created session, so the prompt and tool policy are today's, not a copy.
  const t = await makeClient({ origin, key, tenant, fetch: f, pollMs }).createSession();
  const skills = { ...UPSTREAM_SKILLS, ...(a['--repo'] ? { url: a['--repo'] } : {}), ref: a['--ref'] };
  const direct = buildDirect({ origin, key, template: { agent: t.agent, metadata: t.metadata }, skills, model, extraMcp, tenant });
  const client = makeClient({ origin, key, tenant, fetch: f, pollMs, direct });
  const verifier = a['--no-verify'] ? null : (gold, rec) => verifyCase(gold, rec, { origin, key, model: judgeModel, fetch: f });

  const out = a['--out'];
  console.log(`askbench: ${cases.length} case(s), skills ${skills.url}@${skills.ref}, model ${model}, ${verifier ? `judge ${judgeModel}` : 'no verifier'} → ${out}`);
  const started = new Date().toISOString();
  const r = await runAll({ cases, answers: readJson(ANSWERS), out, client, verifier, secrets: secretsOf({ origin, key }), concurrency: Number(a['--concurrency'] ?? 1), maxUsd, maxMinutes, rerun: !!a['--rerun'], log: console.log });
  let { stopped, not_run } = r;
  if (redoOnly) { // keep what the pass before recorded about cases it never started
    not_run = selected.filter(c => !existsSync(join(out, `${c.id}.json`))).map(c => c.id);
    const prev = existsSync(join(out, 'run.json')) ? readJson(join(out, 'run.json')) : {};
    stopped = not_run.length ? prev.stopped ?? null : null;
  }
  writeFileSync(join(out, 'run.json'), JSON.stringify({ skills, model, judge_model: verifier ? judgeModel : null, started, finished: new Date().toISOString(), max_usd: maxUsd, max_minutes: maxMinutes, spent_usd: Math.round(r.spent * 100) / 100, ran: r.ran, resumed: r.resumed, aborted: r.aborted, stopped, not_run }, null, 1));
  if (r.aborted) { console.error(`askbench: ABORTED, gateway budget exceeded. ${r.not_run.length} case(s) not run: ${r.not_run.join(', ')}`); return 3; }
  if (r.stopped && !redoOnly) console.log(`askbench: stopped at $${r.spent.toFixed(2)} (${r.stopped === 'max-usd' ? `--max-usd ${maxUsd}` : `--max-minutes ${maxMinutes}`}); not run: ${r.not_run.join(', ')}`);
  console.log(`askbench: done, ${r.ran} run, ${r.resumed} resumed, $${r.spent.toFixed(2)}`);
  return 0;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main(process.argv.slice(2)).then(c => process.exit(c), e => { console.error(e.message); process.exit(1); });
