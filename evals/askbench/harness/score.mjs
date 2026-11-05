// score.mjs — the code score: regexes from answers.json run over what Ask TFY showed the user. It is
// cheap, deterministic and offline, but a regex can miss a correct answer in other words, so the verified
// score (verify.mjs) is the headline and this one is the cross-check.
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const rx = s => { try { return new RegExp(s, 'i'); } catch { return new RegExp(String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'); } };
export const anyMatch = (patterns, text) => (patterns ?? []).some(p => typeof p === 'string' && rx(p).test(text));

/**
 * One case. A fact counts once any of its patterns matches the user-visible answers. A fact with no
 * patterns cannot be checked by code (`hit: null`) and is left to the verifier. Solved = every checkable
 * fact, no wrong claim, and the run ended normally.
 */
export function scoreCase(gold, run) {
  const msgs = run.messages ?? [];
  const seen = msgs.map(m => m.text ?? '').join('\n\n');
  const facts = gold.must_include.map(f => ({ fact: f.fact, hit: (f.match ?? []).length ? anyMatch(f.match, seen) : null }));
  const checkable = facts.filter(f => f.hit !== null);
  const wrong = (gold.must_not ?? []).map((f, i) => ({ i, fact: f.fact, claimed: anyMatch(f.match, seen) })).filter(w => w.claimed);
  const ended = msgs.length > 0 && msgs.every(m => m.status === 'done' && (m.text ?? '').trim());
  const recall = checkable.length ? checkable.filter(f => f.hit).length / checkable.length : 0;
  return {
    id: gold.id,
    solved: ended && checkable.length > 0 && recall === 1 && wrong.length === 0,
    recall, facts, wrong, ended,
    ms: msgs.reduce((s, m) => s + (m.ms ?? 0), 0),
    cost_usd: msgs.reduce((s, m) => s + (m.cost_usd ?? 0), 0),
    tool_calls: msgs.reduce((s, m) => s + (m.tool_calls?.length ?? 0), 0),
    tool_errors: msgs.reduce((s, m) => s + (m.tool_errors?.length ?? 0), 0),
    denied_writes: msgs.flatMap(m => m.approvals ?? []).filter(a => a.status === 'deny').length,
  };
}

export const quant = (xs, q) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(q * s.length))]; };
export const round = (x, k = 3) => (x == null ? null : Math.round(x * 10 ** k) / 10 ** k);

/** Case records of a run directory, by id (one <id>.json per case; run.json and the rest are skipped). */
export function loadRun(dir) {
  return Object.fromEntries(readdirSync(dir).filter(f => /^[A-Z]\d+\.json$/.test(f)).map(f => {
    const r = JSON.parse(readFileSync(join(dir, f), 'utf8'));
    return [r.id, r];
  }));
}
