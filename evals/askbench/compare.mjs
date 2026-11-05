// compare.mjs — base vs head on the same cases, as a markdown table.
//
//   node evals/askbench/compare.mjs --base <dir> --head <dir> [--max-drop 2] [--min-coverage 1] [--answers <file>]
//
// Prints the table to stdout and appends it to $GITHUB_STEP_SUMMARY when set.
// Exit 1 when head's solved count (verified, else code) is below base's by more than --max-drop, when head
// makes a must_not claim on a case where base did not, or when fewer than --min-coverage (default 1.0) of
// the cases are comparable. A case is comparable when both arms have a record without a harness error and,
// when verifying, a verifier result in both; the others are listed, never counted as passes.
// Exit 2 on bad input, nothing comparable, or arms that ran with different models or judges.
// A single run is noisy (about 2-3 of 22 questions flip on their own), hence the --max-drop allowance.
import { readFileSync, existsSync, appendFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadRun, scoreCase, quant, round } from './harness/score.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const readJson = p => JSON.parse(readFileSync(p, 'utf8'));
const meta = dir => (existsSync(join(dir, 'run.json')) ? readJson(join(dir, 'run.json')) : null);
const harnessErrored = rec => (rec.messages ?? []).some(m => m.status === 'harness_error');
const goodVerified = rec => (rec.verified && !rec.verified.error ? rec.verified : null);

/** One arm's view of one case: solved, facts hit / total, and the indices of must_not claims it made. */
function view(gold, rec, metric) {
  if (metric === 'verified') {
    const v = goodVerified(rec);
    if (!v) return { solved: false, hit: 0, total: gold.must_include.length, wrong: [], unverified: true };
    return { solved: v.solved, hit: v.facts.filter(f => f.hit).length, total: v.facts.length, wrong: v.wrong.map((w, i) => (w.claimed ? i : -1)).filter(i => i >= 0) };
  }
  const s = scoreCase(gold, rec);
  const checkable = s.facts.filter(f => f.hit !== null);
  return { solved: s.solved, hit: checkable.filter(f => f.hit).length, total: checkable.length, wrong: s.wrong.map(w => w.i) };
}

export function compare(baseDir, headDir, { maxDrop = 2, minCoverage = 1, answers } = {}) {
  const golds = answers ?? readJson(join(HERE, 'answers.json'));
  const base = loadRun(baseDir), head = loadRun(headDir);
  const mb = meta(baseDir), mh = meta(headDir);
  for (const k of ['model', 'judge_model']) {
    if (mb && mh && (mb[k] ?? null) !== (mh[k] ?? null)) return { markdown: `askbench: the arms ran with different ${k} (${mb[k]} vs ${mh[k]}); the comparison is not valid.\n`, exitCode: 2, regressions: [] };
  }
  const anyVerified = [...Object.values(base), ...Object.values(head)].some(goodVerified);
  const metric = anyVerified ? 'verified' : 'code';

  const ids = golds.map(g => g.id).filter(id => base[id] && head[id]);
  const skipped = ids.filter(id => harnessErrored(base[id]) || harnessErrored(head[id]));
  // With the verifier on, a case whose verification failed in either arm cannot be judged either way.
  const unverified = metric === 'verified' ? ids.filter(id => !skipped.includes(id) && !(goodVerified(base[id]) && goodVerified(head[id]))) : [];
  const used = ids.filter(id => !skipped.includes(id) && !unverified.includes(id));
  const missing = golds.map(g => g.id).filter(id => !(base[id] && head[id]));
  if (!used.length) return { markdown: `askbench: no comparable cases (compared 0 of ${golds.length}; missing ${missing.length}, harness errors ${skipped.length}, verifier errors ${unverified.length}).\n`, exitCode: 2, regressions: [] };

  const rows = used.map(id => {
    const g = golds.find(x => x.id === id);
    return { id, area: base[id].area ?? head[id].area ?? '', g, b: view(g, base[id], metric), h: view(g, head[id], metric), br: base[id], hr: head[id] };
  });
  const sum = (k, f) => rows.reduce((s, r) => s + f(r[k], r), 0);
  const total = (k) => ({
    solved: sum(k, v => (v.solved ? 1 : 0)),
    hit: sum(k, v => v.hit), facts: sum(k, v => v.total),
    wrong: sum(k, v => v.wrong.length),
    codeSolved: rows.filter(r => scoreCase(r.g, r[k === 'b' ? 'br' : 'hr']).solved).length,
    p50: round(quant(rows.map(r => (r[k === 'b' ? 'br' : 'hr'].messages ?? []).reduce((s, m) => s + (m.ms ?? 0), 0)), 0.5) / 1000, 1),
    cost: round(rows.reduce((s, r) => s + (r[k === 'b' ? 'br' : 'hr'].messages ?? []).reduce((a, m) => a + (m.cost_usd ?? 0), 0), 0), 2),
  });
  const B = total('b'), H = total('h');

  const regressions = [];
  const label = metric === 'verified' ? 'verified-solved' : 'code-solved';
  const coverage = used.length / golds.length;
  if (coverage < minCoverage - 1e-9) regressions.push(`only ${used.length} of ${golds.length} cases are comparable (coverage ${round(coverage, 2)}, required ${minCoverage})`);
  if (H.solved < B.solved - maxDrop) regressions.push(`${label} fell from ${B.solved} to ${H.solved} (allowed drop ${maxDrop})`);
  for (const r of rows) {
    const fresh = r.h.wrong.filter(i => !r.b.wrong.includes(i));
    for (const i of fresh) regressions.push(`${r.id}: head makes a must_not claim base did not ("${r.g.must_not[i].fact}")`);
  }
  const exitCode = regressions.length ? 1 : 0;

  const yn = v => (v.unverified ? 'unverified' : v.solved ? 'yes' : 'no');
  const delta = r => (r.b.solved === r.h.solved ? '' : r.h.solved ? 'fixed' : 'lost');
  const L = [];
  L.push(`## Ask TFY regression check: ${exitCode ? 'FAIL' : 'PASS'}`, '');
  if (mb || mh) {
    const lab = m => (m ? `${m.skills?.url?.replace(/^https:\/\/github\.com\//, '')}@${m.skills?.ref} (${m.model})` : 'unknown');
    L.push(`- base: ${lab(mb)}`, `- head: ${lab(mh)}`);
  }
  L.push(`- headline: ${metric === 'verified' ? 'verified score (span-bound verifier)' : 'code score only, no verifier results found'}; ${used.length} case(s) compared`);
  for (const [name, m] of [['base', mb], ['head', mh]]) {
    if (m?.aborted) L.push(`- WARNING: ${name} run aborted (${m.aborted}); ${m.not_run?.length ?? 0} case(s) not run`);
    else if (m?.stopped) L.push(`- WARNING: ${name} run stopped at --max-usd; ${m.not_run?.length ?? 0} case(s) not run`);
  }
  if (missing.length) L.push(`- not comparable, missing in one arm: ${missing.join(', ')}`);
  if (skipped.length) L.push(`- not comparable, harness error in an arm (re-run them): ${skipped.join(', ')}`);
  if (unverified.length) L.push(`- not comparable, verifier error in an arm (re-run them): ${unverified.join(', ')}`);
  L.push('');
  if (regressions.length) L.push(...regressions.map(x => `- REGRESSION: ${x}`), '');
  L.push('| Case | Area | Base | Head | Facts base | Facts head | Wrong base | Wrong head | Change |', '|---|---|---|---|---|---|---|---|---|');
  for (const r of rows) L.push(`| ${r.id} | ${r.area} | ${yn(r.b)} | ${yn(r.h)} | ${r.b.hit}/${r.b.total} | ${r.h.hit}/${r.h.total} | ${r.b.wrong.length} | ${r.h.wrong.length} | ${delta(r)} |`);
  L.push('', '| Totals | Base | Head |', '|---|---|---|');
  L.push(`| ${metric === 'verified' ? 'Verified solved' : 'Code solved'} (headline) | ${B.solved}/${used.length} | ${H.solved}/${used.length} |`);
  if (metric === 'verified') L.push(`| Code solved (regex cross-check) | ${B.codeSolved}/${used.length} | ${H.codeSolved}/${used.length} |`);
  L.push(`| Facts hit | ${B.hit}/${B.facts} | ${H.hit}/${H.facts} |`, `| Wrong claims | ${B.wrong} | ${H.wrong} |`, `| Latency p50 (s) | ${B.p50} | ${H.p50} |`, `| Cost (USD) | ${B.cost} | ${H.cost} |`);
  L.push('', `Single runs are noisy (about 2-3 of 22 cases flip without any change); the check fails on a drop above ${maxDrop}, a new wrong claim, or coverage below ${minCoverage}.`, '');
  return { markdown: L.join('\n'), exitCode, regressions };
}

export function main(argv, { env = process.env, out = s => process.stdout.write(s) } = {}) {
  const arg = k => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : undefined; };
  if (argv.includes('--help') || argv.includes('-h') || !arg('--base') || !arg('--head')) {
    out('usage: node evals/askbench/compare.mjs --base <dir> --head <dir> [--max-drop 2] [--min-coverage 1] [--answers <file>]\n');
    return argv.includes('--help') || argv.includes('-h') ? 0 : 2;
  }
  const maxDrop = arg('--max-drop') != null ? Number(arg('--max-drop')) : 2;
  if (!(maxDrop >= 0)) { out('--max-drop must be a number\n'); return 2; }
  const minCoverage = arg('--min-coverage') != null ? Number(arg('--min-coverage')) : 1;
  if (!(minCoverage >= 0 && minCoverage <= 1)) { out('--min-coverage must be between 0 and 1\n'); return 2; }
  let r;
  try { r = compare(arg('--base'), arg('--head'), { maxDrop, minCoverage, answers: arg('--answers') ? readJson(arg('--answers')) : undefined }); } catch (e) { out(`askbench compare: ${e.message}\n`); return 2; }
  out(r.markdown);
  if (env.GITHUB_STEP_SUMMARY) appendFileSync(env.GITHUB_STEP_SUMMARY, r.markdown + '\n');
  return r.exitCode;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) process.exit(main(process.argv.slice(2)));
