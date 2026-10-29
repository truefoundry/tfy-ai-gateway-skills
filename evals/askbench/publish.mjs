// publish.mjs — turns run directories into what may be uploaded from a public repository: per-case scores,
// verdicts with their spans (excerpts of at most 40 words), tool names, latency and cost. Ask TFY's replies,
// the questions and raw error text are not copied, and the control-plane host, keys, bearer tokens and
// email addresses are scrubbed from everything that is.
//
//   node evals/askbench/publish.mjs --in <dir> --out <dir>      (<dir> holds base/ and head/, or is one run)
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { env, redact, secretsOf } from './harness/env.mjs';
import { scoreCase, loadRun } from './harness/score.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const readJson = p => JSON.parse(readFileSync(p, 'utf8'));

/** The publishable form of one case record. `gold` is the case's entry in answers.json (or undefined). */
export function publicRecord(rec, gold, secrets = []) {
  const code = gold ? scoreCase(gold, rec) : null;
  const pub = {
    id: rec.id, area: rec.area, kind: rec.kind,
    messages: (rec.messages ?? []).map(m => ({
      status: m.status,
      error: m.error ? String(m.error).slice(0, 200) : null,
      ms: m.ms ?? 0, cost_usd: m.cost_usd ?? 0, tokens: m.tokens ?? 0,
      clarifications: m.clarifications ?? 0,
      tool_calls: (m.tool_calls ?? []).map(c => ({ name: c.name, thread: c.thread })),
      tool_errors: (m.tool_errors ?? []).map(c => ({ tool: c.tool })),
      approvals: (m.approvals ?? []).map(a => ({ tool: a.tool, status: a.status })),
    })),
    code: code && { solved: code.solved, recall: code.recall, facts: code.facts.map(f => f.hit), wrong: code.wrong.map(w => w.i), ended: code.ended },
    verified: rec.verified ?? null,
  };
  return redact(pub, secrets);
}

function publishDir(inDir, outDir, answers, secrets) {
  mkdirSync(outDir, { recursive: true });
  const gold = Object.fromEntries(answers.map(a => [a.id, a]));
  let n = 0;
  for (const rec of Object.values(loadRun(inDir))) {
    writeFileSync(join(outDir, `${rec.id}.json`), JSON.stringify(publicRecord(rec, gold[rec.id], secrets), null, 1));
    n++;
  }
  if (existsSync(join(inDir, 'run.json'))) writeFileSync(join(outDir, 'run.json'), JSON.stringify(redact(readJson(join(inDir, 'run.json')), secrets), null, 1));
  return n;
}

export function main(argv, { envVars = process.env, log = console.log } = {}) {
  const arg = k => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : undefined; };
  const inDir = arg('--in'), outDir = arg('--out');
  if (!inDir || !outDir) { log('usage: node evals/askbench/publish.mjs --in <dir> --out <dir>'); return 2; }
  if (!existsSync(inDir)) { log(`publish: ${inDir} does not exist, nothing to publish`); return 0; }
  let secrets = [];
  try { secrets = secretsOf(env(envVars)); } catch { /* no env: still scrubs keys, bearers and emails */ }
  const answers = readJson(join(HERE, 'answers.json'));
  const subs = readdirSync(inDir).filter(d => statSync(join(inDir, d)).isDirectory());
  let total = 0;
  if (subs.length) for (const d of subs) total += publishDir(join(inDir, d), join(outDir, d), answers, secrets);
  else total = publishDir(inDir, outDir, answers, secrets);
  log(`publish: ${total} case record(s) → ${outDir}`);
  return 0;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) process.exit(main(process.argv.slice(2)));
