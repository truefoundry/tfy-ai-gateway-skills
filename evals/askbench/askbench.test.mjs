// Offline tests for askbench: fixtures, approval policy, the turn loop against a fake agent runtime, the
// direct rebuild, scoring, the verifier, the run loop (budget abort, spend stop) and compare exit codes.
// No network, no model, no npm packages: `node --test evals/askbench/`.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdirSync, mkdtempSync, existsSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { approvalFor, summarizeEvents, makeClient, isBudgetExceeded } from './harness/client.mjs';
import { buildDirect, configuredName, toHeaderJson } from './harness/direct.mjs';
import { scoreCase, anyMatch } from './harness/score.mjs';
import { spanIn, spanBacks, bindEvidence, verifyPrompt, parseJson, judgeCall, verifyCase } from './harness/verify.mjs';
import { env, redact, secretsOf } from './harness/env.mjs';
import { runAll, runCase, main as runMain, CASES, ANSWERS } from './run.mjs';
import { compare as compareRaw, main as compareMain } from './compare.mjs';
import { publicRecord, main as publishMain } from './publish.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const cases = JSON.parse(readFileSync(CASES, 'utf8'));
const answers = JSON.parse(readFileSync(ANSWERS, 'utf8'));
const tmp = () => mkdtempSync(join(tmpdir(), 'askbench-'));
const reply = (status, body, headers = {}) => ({ ok: status < 400, status, headers, text: async () => JSON.stringify(body) });

/* ------------------------------------------------------------------ fixtures */

test('fixtures: cases.json carries only id/area/kind/ask, and every case has an answer entry', () => {
  assert.equal(cases.length, 22);
  for (const c of cases) assert.deepEqual(Object.keys(c).sort(), ['area', 'ask', 'id', 'kind']);
  assert.deepEqual(cases.map(c => c.id).sort(), answers.map(a => a.id).sort());
  for (const a of answers) {
    assert.deepEqual(Object.keys(a).sort(), ['id', 'must_include', 'must_not', 'verdict'], `${a.id} keys`);
    assert.ok(a.must_include.length > 0, `${a.id} has facts`);
    for (const f of [...a.must_include, ...a.must_not]) {
      assert.deepEqual(Object.keys(f).sort(), ['fact', 'match'], `${a.id} fact keys`);
      assert.ok(f.match.every(m => typeof m === 'string' && (() => { new RegExp(m, 'i'); return true; })()), `${a.id} patterns`);
    }
  }
});

test('fixtures: no must_include pattern matches its own ask (a repeated question must not score)', () => {
  for (const a of answers) {
    const ask = cases.find(c => c.id === a.id).ask;
    for (const f of a.must_include) assert.equal(anyMatch(f.match, ask), false, `${a.id}: "${f.fact.slice(0, 50)}" matches its ask`);
  }
});

test('fixtures: the public tree names no person, internal host, test object or email', () => {
  // Fragments are joined so this file does not trip its own scan.
  const bad = new RegExp([['ca', 'io'].join(''), ['\\bem', 'u\\b'], ['em', 'u-'], ['dev', 'test'], ['truefoundry\\.', 'tech'], '[\\w.+-]+@[\\w-]+\\.[\\w.]+'].map(x => [].concat(x).join('')).join('|'), 'i');
  for (const f of ['cases.json', 'answers.json', 'README.md', '../../.github/workflows/askbench.yml']) {
    const p = join(HERE, f);
    if (existsSync(p)) assert.doesNotMatch(readFileSync(p, 'utf8'), bad, f);
  }
});

/* ------------------------------------------------------------------ approvals */

test('approvals: every write is denied, including prefixed names, wrapped call_tool and unknown tools', () => {
  const wrapped = (server, tool, manifest) => JSON.stringify({ mcp_server: server, tool_name: tool, input: { manifest } });
  const tries = [
    ['apply_manifest', JSON.stringify({ manifest: { name: 'my-va', type: 'virtual-account' } })],
    ['delete_manifest', '{}'],
    ['call_tool', wrapped('tfy-platform-mcp', 'apply_manifest', { name: 'my-va' })],
    ['call_tool', wrapped('tfy-platform-mcp', 'delete_manifest', { name: 'ask-prefixed' })],
    ['call_tool', wrapped('other-mcp', 'apply_manifest', { name: 'x' })],
    ['call_tool', 'not json'],
    ['anything_else', undefined],
  ];
  for (const [tool, args] of tries) assert.equal(approvalFor(tool, args).status, 'deny', tool);
  assert.match(approvalFor('call_tool', wrapped('tfy-platform-mcp', 'apply_manifest', {})).why, /tfy-platform-mcp\/apply_manifest/);
});

function fakeRuntime({ pauseFirst = false, state } = {}) {
  const calls = [];
  let n = 0;
  const turns = {};
  const f = async (url, opts) => {
    const path = new URL(url).pathname.replace(/^.*\/ai-features\/[^/]+/, '').replace(/^\/trueforge\/api\/v1/, '');
    calls.push([opts.method, path, opts.body ? JSON.parse(opts.body) : null, opts.headers]);
    if (opts.method === 'POST' && path === '/sessions') return reply(201, { data: { id: 'S1', agent: { spec: { model: { name: 'tfy-gateway/claude-live-1' }, mcp_servers: [{ name: 'tfy-platform-mcp' }] } }, metadata: { modelIdentifier: 'acct/claude-live-1' } } });
    if (opts.method === 'POST' && path.endsWith('/turns')) {
      const id = `T${++n}`;
      turns[id] = pauseFirst && n === 1
        ? { id, state: { status: 'paused', action_required_on_events: [{ id: 'E9' }] } }
        : { id, state: state ?? { status: 'done', output: { content: 'Use cost_per_month.' }, metrics: { total_tokens: 10, total_cost_in_usd: 0.5 } } };
      return reply(200, { data: { id, state: { status: 'running' } } });
    }
    const m = path.match(/\/turns\/(T\d+)(\/events)?$/);
    if (m && m[2]) {
      const ev = m[1] === 'T1' && pauseFirst
        ? [{ type: 'tool.approval_required', id: 'E9', thread_id: 'main', tool_calls: [{ id: 'c1', function: { name: 'call_tool', arguments: JSON.stringify({ mcp_server: 'tfy-platform-mcp', tool_name: 'apply_manifest', input: { manifest: { name: 'my-va' } } }) } }] }]
        : [{ type: 'model.message', thread_id: 'main', tool_calls: [{ id: 'c2', function: { name: 'search_docs', arguments: '{"query":"secret-ish"}' } }] }];
      return reply(200, { data: ev, pagination: {} });
    }
    if (m) return reply(200, { data: { id: m[1], ...turns[m[1]] } });
    return reply(404, {});
  };
  return { f, calls };
}

test('client: a paused write approval is denied, resumed as a chained turn, metrics sum, tool args are not kept', async () => {
  const { f, calls } = fakeRuntime({ pauseFirst: true });
  const c = makeClient({ origin: 'https://x', key: 'k', fetch: f, pollMs: 0 });
  const s = await c.createSession();
  const r = await c.ask(s.id, 'set a budget');
  assert.equal(r.status, 'done');
  assert.equal(r.text, 'Use cost_per_month.');
  assert.deepEqual(r.approvals.map(a => a.status), ['deny']);
  const second = calls.filter(([m, p]) => m === 'POST' && p.endsWith('/turns'))[1][2];
  assert.equal(second.input[0].type, 'user.tool_approval');
  assert.equal(second.input[0].approval.status, 'deny');
  assert.equal(r.cost_usd, 0.5);
  assert.deepEqual(Object.keys(r.tool_calls[0]).sort(), ['name', 'thread']);
});

test('client: a 502 on a poll is retried, a 502 on a turn POST is not', async () => {
  let polls = 0, posts = 0;
  const f = async (url, opts) => {
    const p = new URL(url).pathname;
    if (opts.method === 'POST' && p.endsWith('/turns')) { posts++; return posts === 1 ? reply(502, {}) : reply(200, { data: { id: 'T1' } }); }
    if (p.endsWith('/events')) return reply(200, { data: [], pagination: {} });
    polls++;
    return polls < 3 ? reply(502, {}) : reply(200, { data: { id: 'T1', state: { status: 'done', output: { content: 'ok' } } } });
  };
  const c = makeClient({ origin: 'https://x', key: 'k', fetch: f, pollMs: 0 });
  await assert.rejects(c.ask('S1', 'q'), /502/);
  assert.equal(posts, 1);
  const r = await c.ask('S1', 'q');
  assert.equal(r.text, 'ok');
  assert.equal(polls, 3);
});

test('client: an ask_user_question turn shows the question, gets one canned reply, and the answer that follows is kept', async () => {
  let n = 0;
  const bodies = [];
  const f = async (url, opts) => {
    const p = new URL(url).pathname;
    if (opts.method === 'POST' && p.endsWith('/turns')) { bodies.push(JSON.parse(opts.body)); return reply(200, { data: { id: `T${++n}` } }); }
    const m = p.match(/\/turns\/(T\d)(\/events)?$/);
    if (m[2]) return reply(200, { pagination: {}, data: m[1] === 'T1'
      ? [{ type: 'model.message', thread_id: 'main', content: 'Which provider?', tool_calls: [{ id: 'q1', function: { name: 'ask_user_question', arguments: '{"question":"Which provider?"}' } }] }]
      : [] });
    return reply(200, { data: { id: m[1], state: m[1] === 'T1'
      ? { status: 'done', output: null, required_actions: [{ type: 'tool.response_required', thread_id: 'main', tool_calls: [{ id: 'q1' }] }] }
      : { status: 'done', output: { content: 'Use cost_per_month.' } } } });
  };
  const c = makeClient({ origin: 'https://x', key: 'k', fetch: f, pollMs: 0 });
  const r = await c.ask('S1', 'q');
  assert.equal(r.clarifications, 1);
  assert.equal(bodies[1].input[0].type, 'user.tool_response');
  assert.match(r.text, /asks the user/);
  assert.match(r.text, /cost_per_month/);
});

test('summarizeEvents: tool names with thread, and error-looking tool responses', () => {
  const ev = [
    { type: 'model.message', thread_id: 'main', tool_calls: [{ id: 't1', function: { name: 'search_docs', arguments: '{"query":"x"}' } }] },
    { type: 'tool.response', tool_call_id: 't1', content: '{"error":"401 Unauthorized"}' },
    { type: 'model.message', thread_id: 'sub-1', tool_calls: [{ id: 't2', function: { name: 'exec', arguments: '{}' } }] },
    { type: 'tool.response', tool_call_id: 't2', content: 'ok' },
  ];
  const s = summarizeEvents(ev);
  assert.deepEqual(s.tool_calls.map(c => [c.name, c.thread]), [['search_docs', 'main'], ['exec', 'sub']]);
  assert.deepEqual(s.tool_errors, [{ tool: 'search_docs' }]);
});

/* ------------------------------------------------------------------ direct rebuild */

const template = {
  agent: { spec: { model: { name: 'tfy-gateway/claude-live-1' }, prompt: 'P', mcp_servers: [{ name: 'tfy-platform-mcp' }, { name: 'tfy-docs-mcp' }] } },
  metadata: { modelIdentifier: 'acct/claude-live-1' },
};

test('direct: the rebuild swaps only the skills mount and the model', () => {
  const a = buildDirect({ origin: 'https://h', key: 'K', template });
  const b = buildDirect({ origin: 'https://h', key: 'K', template, skills: { url: 'https://github.com/x/fork', ref: 'topic', path: 'skills' } });
  assert.deepEqual(a.spec, b.spec);
  for (const h of ['x-tfg-mcp', 'x-tfg-models', 'x-tfy-metadata']) assert.equal(a.headers[h], b.headers[h], h);
  assert.notEqual(a.headers['x-tfg-skills'], b.headers['x-tfg-skills']);
  assert.deepEqual(JSON.parse(b.headers['x-tfg-skills'])['tfy-platform-skills'], { ...JSON.parse(a.headers['x-tfg-skills'])['tfy-platform-skills'], url: 'https://github.com/x/fork', ref: 'topic' });

  const m = buildDirect({ origin: 'https://h', key: 'K', template, model: 'tfy-ai-anthropic/claude-sonnet-5-5' });
  assert.equal(m.spec.model.name, 'tfy-gateway/claude-sonnet-5-5');
  assert.deepEqual({ ...m.spec, model: template.agent.spec.model }, template.agent.spec, 'only spec.model differs');
  assert.deepEqual(JSON.parse(m.headers['x-tfg-models'])['tfy-gateway'].models[0], { model_id: 'tfy-ai-anthropic/claude-sonnet-5-5', name: 'claude-sonnet-5-5', properties: {} });
  assert.equal(m.headers['x-tfg-mcp'], a.headers['x-tfg-mcp']);
  assert.equal(m.headers['x-tfg-skills'], a.headers['x-tfg-skills']);
  assert.equal(template.agent.spec.model.name, 'tfy-gateway/claude-live-1', 'template untouched');
  assert.equal(JSON.parse(a.headers['x-tfg-mcp'])['tfy-platform-mcp'].url, 'https://h/api/svc/truefoundry/mcp');
  assert.equal(JSON.parse(a.headers['x-tfg-mcp'])['tfy-docs-mcp'].auth, undefined);
});

test('direct: unknown MCP servers need ASKBENCH_MCP_EXTRA, a mismatched template is refused, headers stay latin-1', () => {
  const t = { ...template, agent: { spec: { ...template.agent.spec, mcp_servers: [{ name: 'tfy-extra-mcp' }] } } };
  assert.throws(() => buildDirect({ origin: 'https://h', key: 'K', template: t }), /ASKBENCH_MCP_EXTRA/);
  const ok = buildDirect({ origin: 'https://h', key: 'K', template: t, extraMcp: { 'tfy-extra-mcp': { url: 'https://m/mcp' } } });
  assert.equal(JSON.parse(ok.headers['x-tfg-mcp'])['tfy-extra-mcp'].url, 'https://m/mcp');
  assert.throws(() => buildDirect({ origin: 'https://h', key: 'K', template: { ...template, metadata: {} } }), /modelIdentifier/);
  assert.throws(() => buildDirect({ origin: 'https://h', key: 'K', template: { ...template, metadata: { modelIdentifier: 'acct/other' } } }), /does not match/);
  assert.equal(configuredName('anthropic.claude-3.5-sonnet:0'), 'anthropic-claude-3-5-sonnet-0');
  assert.doesNotMatch(toHeaderJson({ d: 'a — b' }), /—/);
});

/* ------------------------------------------------------------------ scoring */

const gold = {
  id: 'R01',
  must_include: [{ fact: 'field', match: ['cost_per_month'] }, { fact: 'type', match: ['tenant-budget-config'] }, { fact: 'prose only', match: [] }],
  must_not: [{ fact: 'v1 field', match: ['budget_limit_usd'] }, { fact: 'prose-only wrong', match: [] }],
};
const msg = (text, extra = {}) => ({ status: 'done', text, ms: 1000, cost_usd: 1, tool_calls: [], tool_errors: [], ...extra });

test('score: solved needs every checkable fact, no wrong claim and a normal end; empty-pattern facts are left to the verifier', () => {
  const a = scoreCase(gold, { messages: [msg('Set cost_per_month in tenant-budget-config.')] });
  assert.equal(a.solved, true);
  assert.deepEqual(a.facts.map(f => f.hit), [true, true, null]);
  const b = scoreCase(gold, { messages: [msg('cost_per_month in tenant-budget-config, or budget_limit_usd')] });
  assert.equal(b.solved, false);
  assert.deepEqual(b.wrong.map(w => w.fact), ['v1 field']);
  assert.equal(scoreCase(gold, { messages: [msg('cost_per_month tenant-budget-config', { status: 'error' })] }).solved, false);
  assert.equal(scoreCase(gold, { messages: [] }).solved, false);
});

/* ------------------------------------------------------------------ verifier */

test('verify: a hit needs a 5-40 word span that is in the reply and about the claim; solved needs every fact, no wrong claim, ended', () => {
  const run = { messages: [{ status: 'done', text: 'Team Managers get **Read Virtual Account** only by default.\nAsk an admin to enable `Manage Virtual Account`, then retry the request.' }] };
  const g = { must_include: [{ fact: 'Team managers only get Read Virtual Account' }, { fact: 'An admin must enable Manage Virtual Account' }], must_not: [{ fact: 'It is a security bug', match: ['security bug'] }] };
  const hit = [{ i: 0, stated: true, span: 'Team Managers get Read Virtual Account only by default' }, { i: 1, stated: true, span: 'Ask an admin to enable Manage Virtual Account' }];
  assert.ok(spanIn('Team Managers get Read Virtual Account only', run.messages[0].text));
  assert.ok(!spanIn('Managers', run.messages[0].text), 'under 3 words is not evidence');
  const ok = bindEvidence({ facts: hit, wrong: [] }, g, run);
  assert.equal(ok.solved, true);
  const invented = bindEvidence({ facts: [hit[0], { i: 1, stated: true, span: 'an admin must make you tenant admin of everything' }], wrong: [{ i: 0, claimed: false, span: '' }] }, g, run);
  assert.deepEqual(invented.facts.map(f => [f.hit, f.dropped]), [[true, false], [false, true]]);
  assert.equal(invented.solved, false);
  const bad = bindEvidence({ facts: hit, wrong: [{ i: 0, claimed: true, span: 'it is a security bug in the gateway' }] }, g, run);
  assert.deepEqual(bad.wrong.map(w => [w.claimed, w.dropped]), [[false, true]], 'an invented wrong-claim span is dropped');
  const claimed = bindEvidence({ facts: hit, wrong: [{ i: 0, claimed: true, span: 'Manage Virtual Account, then retry the request.' }] }, { ...g, must_not: [{ fact: 'Says retry after enabling is wrong', match: ['retry the request'] }] }, run);
  assert.equal(claimed.solved, false, 'a wrong claim backed by a real, relevant span fails the case');
  assert.equal(bindEvidence({ facts: hit, wrong: [] }, g, { messages: [{ ...run.messages[0], status: 'timeout' }] }).solved, false);
});

test('verify: an unrelated in-reply span, the whole reply, and a too-short span are not evidence; a paraphrase and a regex-only match are', () => {
  const text = 'Tools are renamed `<original_tool_name>_<server_identifier>` to avoid collisions. Unrelated sentence about billing cycles and invoices follows here today.';
  const fact = 'Tool names get a short server identifier appended';
  assert.equal(spanBacks('Tools are renamed `<original_tool_name>_<server_identifier>` to avoid collisions', text, fact), true, 'plural/identifier paraphrase shares "tool"');
  assert.equal(spanBacks('Unrelated sentence about billing cycles and invoices follows', text, fact), false, 'in the reply but about something else');
  const whole = `${text} ${Array.from({ length: 30 }, (_, i) => `filler${i}`).join(' ')}`;
  assert.equal(spanBacks(whole, whole, fact), false, 'a whole reply over 40 words, even one that mentions the fact');
  assert.equal(spanBacks(text, text, fact), true, 'the same text under 40 words is a legal span');
  const long = Array.from({ length: 45 }, (_, i) => `tool${i}`).join(' ');
  assert.equal(spanBacks(long, long, 'tool0 names'), false, '41+ words');
  assert.equal(spanBacks('Tools are renamed', text, fact), false, 'under 5 words');
  assert.equal(spanBacks('renamed with suffix to avoid collisions', text + ' renamed with suffix to avoid collisions', 'unrelated claim words', ['suffix']), true, 'a regex of the claim backs it');
  assert.equal(spanBacks('renamed with suffix to avoid collisions', text + ' renamed with suffix to avoid collisions', 'unrelated claim words', ['nomatch']), false);
  const g = { must_include: [{ fact, match: [] }], must_not: [] };
  const r = bindEvidence({ facts: [{ i: 0, stated: true, span: 'Unrelated sentence about billing cycles and invoices follows' }] }, g, { messages: [{ status: 'done', text }] });
  assert.deepEqual([r.facts[0].hit, r.facts[0].dropped, r.solved], [false, true, false]);
});

test('verify: the prompt carries the facts and replies but not the code-side regexes; JSON is found inside a fence', () => {
  const p = verifyPrompt({ must_include: [{ fact: 'F0', match: ['SECRET_REGEX'] }], must_not: [{ fact: 'W0', match: ['SECRET_REGEX'] }] }, { messages: [{ user: 'Q?', text: 'A.' }] });
  assert.match(p, /0\. F0/);
  assert.match(p, /0\. W0/);
  assert.doesNotMatch(p, /SECRET_REGEX/);
  assert.deepEqual(parseJson('```json\n{"facts":[]}\n```'), { facts: [] });
  assert.throws(() => parseJson('no json'), /no JSON/);
});

test('verify: calls the gateway chat completions at temperature 0 with the judge model; a budget 429 surfaces', async () => {
  const seen = [];
  const f = async (url, init) => {
    seen.push([url, init.headers.Authorization, JSON.parse(init.body)]);
    return reply(200, { choices: [{ message: { content: 'Sure: {"facts":[{"i":0,"stated":true,"span":"use the cost per month field"}],"wrong":[]}' } }] });
  };
  const g = { must_include: [{ fact: 'Use the cost per month field' }], must_not: [] };
  const run = { messages: [{ user: 'q', status: 'done', text: 'Please use the cost per month field here.' }] };
  const v = await verifyCase(g, run, { origin: 'https://h', key: 'K', model: 'acct/judge', fetch: f });
  assert.equal(v.solved, true);
  assert.equal(seen[0][0], 'https://h/api/llm/api/inference/openai/chat/completions');
  assert.equal(seen[0][1], 'Bearer K');
  assert.equal(seen[0][2].temperature, 0);
  assert.equal(seen[0][2].model, 'acct/judge');
  const budget = async () => reply(429, { error: { message: 'Budget exceeded for tenant' } });
  await assert.rejects(judgeCall('p', { origin: 'https://h', key: 'K', model: 'm', fetch: budget }), e => isBudgetExceeded(e.message));
  let n = 0;
  const flaky = async () => (++n < 3 ? reply(502, {}) : reply(200, { choices: [{ message: { content: '{}' } }] }));
  assert.equal(await judgeCall('p', { origin: 'https://h', key: 'K', model: 'm', fetch: flaky, sleepMs: 0 }), '{}');
});

/* ------------------------------------------------------------------ run loop */

const fakeClient = (impl) => ({ createSession: async () => ({ id: 'S', agent: { spec: { model: { name: 'm' } } } }), ask: impl });
const okAnswer = (cost = 1) => async () => ({ status: 'done', text: 'an answer', ms: 5, cost_usd: cost, tokens: 1, tool_calls: [], tool_errors: [], approvals: [] });

test('run: the first gateway budget 429 aborts the whole run; no new case starts after it', async () => {
  const out = tmp();
  let started = 0;
  const client = fakeClient(async () => { started++; throw new Error('askbench: POST /sessions/S/turns → 429 {"error":"Budget exceeded for virtual account"}'); });
  const r = await runAll({ cases: cases.slice(0, 5), answers, out, client, concurrency: 1 });
  assert.equal(r.aborted, 'budget');
  assert.equal(started, 1);
  assert.deepEqual(r.not_run, cases.slice(1, 5).map(c => c.id));
  const rec = JSON.parse(readFileSync(join(out, 'R01.json'), 'utf8'));
  assert.equal(rec.messages[0].status, 'harness_error');
  assert.equal(readdirSync(out).length, 1, 'only the failed case is on disk, and a rerun redoes it');
});

test('run: a budget 429 reported by the turn itself, or by the verifier, also aborts', async () => {
  const turnErr = fakeClient(async () => ({ status: 'error', error: 'Budget exceeded', text: '', ms: 1, cost_usd: 0, tool_calls: [], tool_errors: [], approvals: [] }));
  assert.equal((await runAll({ cases: cases.slice(0, 3), answers, out: tmp(), client: turnErr })).aborted, 'budget');
  const verifier = async () => { throw new Error('verifier: 429 Budget exceeded'); };
  const r = await runAll({ cases: cases.slice(0, 3), answers, out: tmp(), client: fakeClient(okAnswer()), verifier });
  assert.equal(r.aborted, 'budget');
  assert.equal(r.ran, 1);
});

test('run: stops starting cases once spend reaches --max-usd, and a rerun resumes the rest', async () => {
  const out = tmp();
  const client = fakeClient(okAnswer(2.5));
  const r = await runAll({ cases: cases.slice(0, 6), answers, out, client, maxUsd: 5 });
  assert.equal(r.stopped, 'max-usd');
  assert.equal(r.ran, 2);
  assert.equal(r.spent, 5);
  assert.deepEqual(r.not_run, cases.slice(2, 6).map(c => c.id));
  const r2 = await runAll({ cases: cases.slice(0, 3), answers, out, client, maxUsd: 100 });
  assert.equal(r2.ran, 1);
  assert.equal(r2.resumed, 2);
});

test('run: only the verifier re-runs on a settled case whose verification failed; records are redacted', async () => {
  const out = tmp();
  let asks = 0;
  const client = fakeClient(async () => { asks++; return { status: 'done', text: 'leaked sk-KEY123 and Bearer abcdefghijklmnopqrstuvwxyz', ms: 1, cost_usd: 0, tool_calls: [], tool_errors: [], approvals: [] }; });
  let fail = true;
  const verifier = async (g, rec) => { if (fail) throw new Error('boom'); return { facts: [], wrong: [], ended: true, solved: true }; };
  await runAll({ cases: cases.slice(0, 1), answers, out, client, verifier, secrets: ['sk-KEY123'] });
  const first = readFileSync(join(out, 'R01.json'), 'utf8');
  assert.doesNotMatch(first, /sk-KEY123|abcdefghijklmnopqrstuvwxyz/);
  assert.equal(JSON.parse(first).verified.error, 'boom');
  fail = false;
  await runAll({ cases: cases.slice(0, 1), answers, out, client, verifier });
  assert.equal(asks, 1, 'the question was not asked again');
  assert.equal(JSON.parse(readFileSync(join(out, 'R01.json'), 'utf8')).verified.solved, true);
});

test('run: a failed session create is recorded as a harness error, not thrown', async () => {
  const client = { createSession: async () => { throw new Error('askbench: POST /sessions → 401 nope'); }, ask: okAnswer() };
  const rec = await runCase(client, cases[0]);
  assert.equal(rec.messages[0].status, 'harness_error');
});

test('run main: builds the direct agent with the requested ref and model, writes run.json, exits 0; --help works', async () => {
  const { f, calls } = fakeRuntime();
  const out = tmp();
  const envVars = { ASKBENCH_TFY_HOST: 'https://host.example/api/llm', ASKBENCH_TFY_API_KEY: 'K' };
  const code = await runMain(['--ref', 'topic', '--repo', 'https://github.com/x/fork', '--out', out, '--only', 'R01,R02', '--no-verify', '--model', 'acct/claude-sonnet-5-5'], { fetch: f, envVars, pollMs: 0 });
  assert.equal(code, 0);
  const directCreate = calls.filter(([m, p, , h]) => m === 'POST' && p === '/sessions' && h['x-tfg-skills']);
  assert.equal(directCreate.length, 2);
  assert.deepEqual(JSON.parse(directCreate[0][3]['x-tfg-skills'])['tfy-platform-skills'].ref, 'topic');
  assert.equal(directCreate[0][2].agent.spec.model.name, 'tfy-gateway/claude-sonnet-5-5');
  const meta = JSON.parse(readFileSync(join(out, 'run.json'), 'utf8'));
  assert.equal(meta.skills.url, 'https://github.com/x/fork');
  assert.equal(meta.aborted, null);
  assert.doesNotMatch(readFileSync(join(out, 'run.json'), 'utf8'), /host\.example|"K"/);
  assert.equal(readdirSync(out).filter(x => /^R\d+\.json$/.test(x)).length, 2);
  assert.equal(await runMain(['--help']), 0);
  await assert.rejects(runMain(['--out', out], { envVars }), /--ref and --out/);
  await assert.rejects(runMain(['--ref', 'x', '--out', out, '--only', 'R99'], { fetch: f, envVars, pollMs: 0 }), /unknown case id/);
});

test('env and redact: host with or without path, missing vars, keys and bearer tokens scrubbed', () => {
  assert.equal(env({ ASKBENCH_TFY_HOST: 'https://h.example/api/llm', ASKBENCH_TFY_API_KEY: 'K' }).origin, 'https://h.example');
  assert.equal(env({ ASKBENCH_TFY_HOST: 'h.example', ASKBENCH_TFY_API_KEY: 'K' }).origin, 'https://h.example');
  assert.throws(() => env({}), /ASKBENCH_TFY_HOST/);
  const r = redact({ text: 'key=SECRETKEY1234 Bearer abcdefghijklmnopqrstuvwxyz0123', authorization: 'x', n: 3 }, 'SECRETKEY1234');
  assert.deepEqual(r, { text: 'key=<redacted> Bearer <redacted>', authorization: '<redacted>', n: 3 });
  const host = redact('see https://h.example/api and h.example, mail me at a.b' + String.fromCharCode(64) + 'corp.example', secretsOf({ origin: 'https://h.example', key: 'K' }));
  assert.equal(host, 'see <redacted>/api and <redacted>, mail me at <redacted-email>');
});

/* ------------------------------------------------------------------ compare */

/** A synthetic run dir: `spec` maps case id -> {solved, wrong: [must_not indices], ms, cost}. */
function mkRun(spec, extra = {}) {
  const dir = tmp();
  for (const [id, s] of Object.entries(spec)) {
    const g = answers.find(a => a.id === id);
    const rec = {
      id, area: cases.find(c => c.id === id).area, kind: 'troubleshoot',
      messages: [{ user: 'q', status: s.harness ? 'harness_error' : 'done', text: s.harness ? '' : 'a reply', ms: s.ms ?? 1000, cost_usd: s.cost ?? 1, tool_calls: [], tool_errors: [], approvals: [] }],
      ...(s.noVerify ? {} : { verified: { facts: g.must_include.map(() => ({ hit: !!s.solved })), wrong: g.must_not.map((_, i) => ({ claimed: (s.wrong ?? []).includes(i) })), ended: true, solved: !!s.solved && !(s.wrong ?? []).length } }),
    };
    writeFileSync(join(dir, `${id}.json`), JSON.stringify(rec));
  }
  if (extra.meta) writeFileSync(join(dir, 'run.json'), JSON.stringify(extra.meta));
  return dir;
}
// The small synthetic dirs below hold a few cases, so coverage is waived except in the coverage tests.
const compare = (b, h, o = {}) => compareRaw(b, h, { minCoverage: 0, ...o });
const ids = n => cases.slice(0, n).map(c => c.id);
const all = (n, f) => Object.fromEntries(ids(n).map((id, i) => [id, f(i)]));

test('compare: equal runs pass and print the per-case table, totals, latency p50 and cost', () => {
  const base = mkRun(all(6, i => ({ solved: i < 4, ms: 1000 * (i + 1), cost: 2 })));
  const head = mkRun(all(6, i => ({ solved: i < 4, ms: 1000 * (i + 1), cost: 2 })));
  const r = compare(base, head);
  assert.equal(r.exitCode, 0);
  assert.match(r.markdown, /\| R01 \| access-identity \| yes \| yes \|/);
  assert.match(r.markdown, /Verified solved \(headline\) \| 4\/6 \| 4\/6/);
  assert.match(r.markdown, /Latency p50 \(s\) \| 4 \| 4/);
  assert.match(r.markdown, /Cost \(USD\) \| 12 \| 12/);
  assert.match(r.markdown, /PASS/);
});

test('compare: exit 1 only when head loses more than --max-drop verified-solved cases', () => {
  const base = mkRun(all(8, () => ({ solved: true })));
  const drop = n => mkRun(all(8, i => ({ solved: i >= n })));
  assert.equal(compare(base, drop(2)).exitCode, 0, 'a drop of 2 is inside the default allowance');
  const three = compare(base, drop(3));
  assert.equal(three.exitCode, 1);
  assert.match(three.markdown, /FAIL/);
  assert.match(three.markdown, /\| lost \|/);
  assert.equal(compare(base, drop(3), { maxDrop: 3 }).exitCode, 0);
  assert.equal(compare(base, drop(1), { maxDrop: 0 }).exitCode, 1);
  assert.equal(compare(drop(3), base).exitCode, 0, 'an improvement passes');
});

test('compare: a must_not claim head makes and base did not fails even when the solved count holds', () => {
  const g = answers.find(a => a.id === 'R01');
  assert.ok(g.must_not.length >= 2);
  const base = mkRun({ R01: { solved: false, wrong: [0] }, R02: { solved: true } });
  const sameClaim = mkRun({ R01: { solved: false, wrong: [0] }, R02: { solved: true } });
  assert.equal(compare(base, sameClaim).exitCode, 0, 'a claim base also made is not new');
  const newClaim = mkRun({ R01: { solved: false, wrong: [0, 1] }, R02: { solved: true } });
  const r = compare(base, newClaim);
  assert.equal(r.exitCode, 1);
  assert.match(r.markdown, /REGRESSION: R01: head makes a must_not claim base did not/);
});

test('compare: only cases present and error-free in both arms count; nothing comparable is exit 2; no verifier falls back to code', () => {
  const base = mkRun({ R01: { solved: true }, R02: { solved: true }, R03: { solved: true } });
  const head = mkRun({ R01: { solved: true }, R02: { harness: true }, R05: { solved: true } });
  const r = compare(base, head);
  assert.match(r.markdown, /missing in one arm: R03/);
  assert.match(r.markdown, /harness error in an arm \(re-run them\): R02/);
  assert.match(r.markdown, /1 case\(s\) compared/);
  assert.equal(compare(mkRun({ R01: { solved: true } }), mkRun({ R05: { solved: true } })).exitCode, 2);
  const code = compare(mkRun({ R01: { noVerify: true } }), mkRun({ R01: { noVerify: true } }));
  assert.match(code.markdown, /code score only/);
  assert.match(code.markdown, /code-solved|Code solved/);
});

test('compare: warns when a run aborted or stopped at the spend cap', () => {
  const meta = { skills: { url: 'https://github.com/o/r', ref: 'b' }, model: 'acct/m', stopped: 'max-usd', not_run: ['R05'] };
  const r = compare(mkRun({ R01: { solved: true } }, { meta }), mkRun({ R01: { solved: true } }, { meta: { ...meta, stopped: null, aborted: 'budget' } }));
  assert.match(r.markdown, /base: o\/r@b \(acct\/m\)/);
  assert.match(r.markdown, /WARNING: base run stopped at --max-usd/);
  assert.match(r.markdown, /WARNING: head run aborted \(budget\)/);
});

test('compare CLI: exit codes, stdout table, and $GITHUB_STEP_SUMMARY', () => {
  const base = mkRun(all(8, () => ({ solved: true })));
  const bad = mkRun(all(8, i => ({ solved: i >= 4 })));
  const summary = join(tmp(), 'summary.md');
  let out = '';
  assert.equal(compareMain(['--base', base, '--head', bad, '--min-coverage', '0'], { env: { GITHUB_STEP_SUMMARY: summary }, out: s => { out += s; } }), 1);
  assert.match(out, /\| Case \| Area \|/);
  assert.equal(readFileSync(summary, 'utf8').includes('FAIL'), true);
  assert.equal(compareMain(['--base', base, '--head', base, '--max-drop', '0', '--min-coverage', '0'], { env: {}, out: () => {} }), 0);
  assert.equal(compareMain(['--base', base, '--head', base, '--max-drop', '0'], { env: {}, out: () => {} }), 1, 'default coverage is 1.0: 8 of 22 cases fail');
  assert.equal(compareMain(['--base', base, '--head', base, '--min-coverage', '2'], { env: {}, out: () => {} }), 2);
  assert.equal(compareMain(['--base', base], { env: {}, out: () => {} }), 2);
  assert.equal(compareMain(['--base', base, '--head', '/nonexistent/dir'], { env: {}, out: () => {} }), 2);
});

/* ------------------------------------------------------------------ coverage, verifier errors, arms */

/** A full 22-case run directory, `f(i)` giving each case's spec. */
const full = (f, extra) => mkRun(Object.fromEntries(cases.map((c, i) => [c.id, f(i)])), extra);

test('compare: default coverage is every case; a partial run, a stopped arm or a harness error is a failure, --min-coverage relaxes it', () => {
  const base = full(() => ({ solved: true }));
  assert.equal(compareRaw(base, full(() => ({ solved: true }))).exitCode, 0);
  const partial = mkRun(Object.fromEntries(cases.slice(0, 20).map(c => [c.id, { solved: true }])), { meta: { model: 'm', stopped: 'max-usd', not_run: ['R22', 'R23'] } });
  const r = compareRaw(base, partial);
  assert.equal(r.exitCode, 1);
  assert.match(r.markdown, /only 20 of 22 cases are comparable/);
  assert.match(r.markdown, /missing in one arm: R22, R23/);
  assert.equal(compareRaw(base, partial, { minCoverage: 0.9 }).exitCode, 0);
  const errored = full(i => (i === 3 ? { harness: true } : { solved: true }));
  assert.equal(compareRaw(base, errored).exitCode, 1);
  assert.match(compareRaw(base, errored).markdown, /harness error in an arm \(re-run them\): R04/);
});

test('compare: a case whose verifier errored in an arm is not comparable, never "no wrong claims"', () => {
  const g = answers.find(a => a.id === 'R01');
  const dir = (verified) => { const d = mkRun({ R01: { solved: true }, R02: { solved: true } }); const f = join(d, 'R01.json'); const rec = JSON.parse(readFileSync(f, 'utf8')); rec.verified = verified; writeFileSync(f, JSON.stringify(rec)); return d; };
  const base = dir({ facts: g.must_include.map(() => ({ hit: true })), wrong: g.must_not.map(() => ({ claimed: false })), ended: true, solved: true });
  const head = dir({ error: 'verifier: 502' });
  const r = compare(base, head);
  assert.match(r.markdown, /verifier error in an arm \(re-run them\): R01/);
  assert.match(r.markdown, /1 case\(s\) compared/);
  assert.equal(compareRaw(base, head).exitCode, 1, 'with full coverage required it fails');
});

test('compare: arms that ran with different models or judges are refused (exit 2)', () => {
  const mk = m => mkRun({ R01: { solved: true } }, { meta: m });
  assert.equal(compare(mk({ model: 'a', judge_model: 'j' }), mk({ model: 'b', judge_model: 'j' })).exitCode, 2);
  assert.equal(compare(mk({ model: 'a', judge_model: 'j' }), mk({ model: 'a', judge_model: 'k' })).exitCode, 2);
  assert.equal(compare(mk({ model: 'a', judge_model: 'j' }), mk({ model: 'a', judge_model: 'j' })).exitCode, 0);
});

test('compare: the regression text names the metric in use', () => {
  const r = compare(mkRun(all(5, () => ({ noVerify: true }))), mkRun(all(5, () => ({ noVerify: true }))));
  assert.match(r.markdown, /code score only/);
});

/* ------------------------------------------------------------------ artifact */

test('publish: the artifact form holds scores, verdicts, spans, tool names, latency and cost, and no reply text, question, host or key', () => {
  const rec = {
    id: 'R01', area: 'access-identity', kind: 'troubleshoot',
    messages: [{ user: 'SECRET QUESTION TEXT', status: 'done', text: 'SECRET REPLY TEXT from https://h.example with sk-KEY123 and a' + String.fromCharCode(64) + 'corp.example', error: 'failed calling https://h.example/api', ms: 1234, cost_usd: 1.5, tokens: 99, clarifications: 0, tool_calls: [{ name: 'search_docs', thread: 'main' }], tool_errors: [{ tool: 'search_docs' }], approvals: [{ tool: 'call_tool', status: 'deny', why: 'detail https://h.example' }] }],
    verified: { facts: [{ hit: true, span: 'a short evidence span at https://h.example here', dropped: false }], wrong: [], ended: true, solved: true, model: 'acct/judge' },
  };
  const pub = publicRecord(rec, answers.find(a => a.id === 'R01'), secretsOf({ origin: 'https://h.example', key: 'sk-KEY123' }));
  const text = JSON.stringify(pub);
  assert.doesNotMatch(text, /SECRET|sk-KEY123|h\.example|corp\.example/);
  assert.equal(pub.messages[0].ms, 1234);
  assert.equal(pub.messages[0].cost_usd, 1.5);
  assert.deepEqual(pub.messages[0].tool_calls, [{ name: 'search_docs', thread: 'main' }]);
  assert.equal(pub.verified.facts[0].span, 'a short evidence span at <redacted> here');
  assert.equal(typeof pub.code.solved, 'boolean');
  for (const m of pub.messages) { assert.equal('text' in m, false); assert.equal('user' in m, false); }
});

test('publish CLI: writes base/ and head/ without reply text, skips a missing input, needs --in and --out', () => {
  const root = tmp();
  for (const arm of ['base', 'head']) {
    const d = join(root, arm); mkdirSync(d);
    writeFileSync(join(d, 'R01.json'), JSON.stringify({ id: 'R01', messages: [{ user: 'Q?', status: 'done', text: 'ONLY IN THE PRIVATE COPY', ms: 1, cost_usd: 0, tool_calls: [], tool_errors: [] }] }));
    writeFileSync(join(d, 'run.json'), JSON.stringify({ skills: { url: 'https://github.com/o/r', ref: arm } }));
  }
  const out = join(tmp(), 'pub');
  const logs = [];
  assert.equal(publishMain(['--in', root, '--out', out], { envVars: {}, log: x => logs.push(x) }), 0);
  for (const arm of ['base', 'head']) {
    assert.deepEqual(readdirSync(join(out, arm)).sort(), ['R01.json', 'run.json']);
    assert.doesNotMatch(readFileSync(join(out, arm, 'R01.json'), 'utf8'), /PRIVATE COPY|Q\?/);
  }
  assert.equal(publishMain(['--in', join(root, 'nope'), '--out', out], { envVars: {}, log: () => {} }), 0);
  assert.equal(publishMain([], { envVars: {}, log: () => {} }), 2);
});

/* ------------------------------------------------------------------ run loop, second pass and clock */

test('run: spend already in --out counts toward the cap, and --max-minutes stops starting cases', async () => {
  const out = tmp();
  const client = fakeClient(okAnswer(2));
  await runAll({ cases: cases.slice(0, 2), answers, out, client });
  const r = await runAll({ cases: cases.slice(0, 5), answers, out, client, maxUsd: 5 });
  assert.equal(r.ran, 1, 'only one more case fits under the cap of 5 after 4 already spent');
  assert.equal(r.stopped, 'max-usd');
  let t = 0;
  const r2 = await runAll({ cases: cases.slice(0, 4), answers, out: tmp(), client, maxMinutes: 1, now: () => (t += 40000) });
  assert.equal(r2.stopped, 'max-minutes');
  assert.ok(r2.ran >= 1 && r2.ran < 4);
});

test('run main --redo-only: redoes a harness error already on disk, never starts new cases, keeps what the first pass recorded', async () => {
  const { f } = fakeRuntime();
  const out = tmp();
  const envVars = { ASKBENCH_TFY_HOST: 'https://host.example', ASKBENCH_TFY_API_KEY: 'K' };
  writeFileSync(join(out, 'R01.json'), JSON.stringify({ id: 'R01', messages: [{ user: 'q', status: 'harness_error', error: 'boom', text: '', ms: 0, cost_usd: 0, tool_calls: [], tool_errors: [] }] }));
  writeFileSync(join(out, 'run.json'), JSON.stringify({ stopped: 'max-usd', not_run: ['R02'] }));
  const code = await runMain(['--ref', 'x', '--out', out, '--only', 'R01,R02', '--no-verify', '--redo-only'], { fetch: f, envVars, pollMs: 0 });
  assert.equal(code, 0);
  assert.equal(JSON.parse(readFileSync(join(out, 'R01.json'), 'utf8')).messages[0].status, 'done');
  assert.equal(existsSync(join(out, 'R02.json')), false);
  const meta = JSON.parse(readFileSync(join(out, 'run.json'), 'utf8'));
  assert.deepEqual([meta.stopped, meta.not_run], ['max-usd', ['R02']]);
});

/* ------------------------------------------------------------------ workflow */

test('workflow: concurrency sits on the job, not the workflow; secrets are not in the unit-test job; artifact is the scrubbed dir', () => {
  const wf = readFileSync(join(HERE, '..', '..', '.github', 'workflows', 'askbench.yml'), 'utf8');
  assert.doesNotMatch(wf, /^concurrency:/m);
  assert.match(wf, /^    concurrency:\n      group: askbench-/m);
  const unit = wf.slice(wf.indexOf('  unit:'), wf.indexOf('  askbench:'));
  assert.doesNotMatch(unit, /secrets\./);
  assert.match(wf, /path: askbench-public\//);
  assert.match(wf, /retention-days: 7/);
  assert.doesNotMatch(wf, /path: askbench-out/);
  assert.match(wf, /--redo-only/);
});
