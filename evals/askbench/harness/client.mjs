// client.mjs — drives Ask TFY the way the console does. The platform API creates the session (inline
// agent, owner metadata, gateway token) and proxies every turn to the agent runtime; `direct` skips that
// proxy and talks to the same runtime with an agent built by direct.mjs, so one input (the skills git ref)
// can change before it is merged.
//
// Turns are created with stream:false and polled, because an SSE stream can be dropped after a minute
// on some installs and a poll survives that. `fetch` is injectable for tests.

const sleep = ms => new Promise(r => setTimeout(r, ms));

/**
 * What the driver answers when Ask TFY asks for approval: always no. The benchmark is read-only, so a
 * write the agent attempts is denied and recorded; an attempted write on a question is itself a finding.
 * The platform tools are lazy-loaded behind call_tool, so the inner tool is named in the reason.
 */
export function approvalFor(toolName, args) {
  let inner = toolName;
  if (toolName === 'call_tool') {
    let a = args;
    if (typeof a === 'string') { try { a = JSON.parse(a); } catch { a = null; } }
    inner = a?.tool_name ? `${a.mcp_server ?? '?'}/${a.tool_name}` : 'call_tool';
  }
  return { status: 'deny', why: `askbench is read-only: ${inner}` };
}

/** True when a record, error text or response body says the gateway budget is spent. */
export const isBudgetExceeded = text => /budget exceeded/i.test(String(text ?? ''));

/** Flattens a turn's persisted events into what scoring needs; no tool arguments or outputs are kept. */
export function summarizeEvents(events) {
  const tool_calls = [], tool_errors = [];
  const byId = new Map();
  for (const raw of events) {
    const e = raw.event ?? raw;
    if (e.type === 'model.message' && Array.isArray(e.tool_calls)) {
      for (const c of e.tool_calls) {
        const call = { id: c.id, name: c.function?.name ?? c.name, thread: e.thread_id === 'main' ? 'main' : 'sub' };
        tool_calls.push({ name: call.name, thread: call.thread });
        byId.set(c.id, call);
      }
    }
    if (e.type === 'tool.response') {
      const text = typeof e.content === 'string' ? e.content : JSON.stringify(e.content ?? '');
      if (/^\s*(error|\{"error")|"isError"\s*:\s*true|\b(4\d\d|5\d\d) (unauthori[sz]ed|forbidden|not found|internal server error)\b/i.test(text.slice(0, 400))) {
        tool_errors.push({ tool: byId.get(e.tool_call_id)?.name ?? null });
      }
    }
  }
  return { tool_calls, tool_errors };
}

export const outputText = state => {
  const c = state?.output?.content;
  if (typeof c === 'string') return c;
  if (Array.isArray(c)) return c.map(p => p.text ?? p.refusal ?? '').join('');
  return '';
};

/** What a user with no more context says to a clarifying question; the benchmark asks are self-contained. */
export const CLARIFY_REPLY = 'I have no further details. Please proceed with sensible defaults and tell me what you assumed.';

const textOf = c => (typeof c === 'string' ? c : Array.isArray(c) ? c.map(p => p.text ?? p.refusal ?? '').join('') : '');

/**
 * What the console shows for one turn: the final output, or — when the turn ended on a client tool such
 * as ask_user_question — the last main-thread message text plus the question itself.
 */
export function visibleText(state, flat, callsById, open) {
  const out = outputText(state);
  if (out.trim()) return out;
  const main = flat.filter(e => e.type === 'model.message' && e.thread_id === 'main' && textOf(e.content).trim());
  const body = main.length ? textOf(main.at(-1).content) : '';
  const questions = open.filter(a => a.type === 'tool.response_required').flatMap(a => a.tool_calls ?? [])
    .map(r => callsById.get(r.id)).filter(c => (c?.function?.name ?? c?.name) === 'ask_user_question')
    .map(c => { const a = c.function?.arguments; return typeof a === 'string' ? a : JSON.stringify(a ?? ''); });
  return [body, ...questions.map(q => `[asks the user] ${q}`)].filter(Boolean).join('\n\n');
}

export function makeClient({ origin, key, tenant = 'truefoundry', fetch: f = fetch, pollMs = 5000, turnTimeoutMs = 30 * 60 * 1000, direct = null }) {
  const base = direct ? `${origin}/trueforge/api/v1` : `${origin}/api/svc/v1/ai-features/${tenant}`;
  const H = { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json', ...(direct?.headers ?? {}) };
  // The agent runtime sits behind a proxy that has 502 windows while it redeploys. Reads and session
  // creates are retried through one; a turn POST is not, since a retry would run the question twice — a
  // failed one is recorded as a harness error and the case re-run with --only.
  const req = async (method, path, body, { retries = method === 'GET' || path === '/sessions' ? 6 : 0 } = {}) => {
    for (let attempt = 0; ; attempt++) {
      let r, text;
      try {
        r = await f(base + path, { method, headers: H, ...(body ? { body: JSON.stringify(body) } : {}) });
        text = await r.text();
      } catch (e) {
        if (attempt < retries) { await sleep(Math.min(60000, 5000 * 2 ** attempt) * (pollMs ? 1 : 0)); continue; }
        throw new Error(`askbench: ${method} ${path} → network ${e.message}`);
      }
      if (r.status >= 500 && attempt < retries) { await sleep(Math.min(60000, 5000 * 2 ** attempt) * (pollMs ? 1 : 0)); continue; }
      let json; try { json = JSON.parse(text); } catch { json = null; }
      if (!r.ok) throw new Error(`askbench: ${method} ${path} → ${r.status} ${text.slice(0, 300)}`);
      return json;
    }
  };

  const events = async (sid, tid) => {
    const all = [];
    let pt;
    do {
      const j = await req('GET', `/sessions/${sid}/turns/${tid}/events?limit=100&order=asc${pt ? `&page_token=${encodeURIComponent(pt)}` : ''}`);
      all.push(...(j.data ?? []));
      pt = j.pagination?.next_page_token;
    } while (pt);
    return all;
  };

  const waitTurn = async (sid, tid, t0) => {
    for (;;) {
      const j = await req('GET', `/sessions/${sid}/turns/${tid}`);
      if (j.data.state.status !== 'running') return j.data;
      if (Date.now() - t0 > turnTimeoutMs) return { ...j.data, state: { status: 'timeout' } };
      await sleep(pollMs);
    }
  };

  /**
   * One user message, run to a terminal state. Approval pauses are denied (approvalFor) and resumed as
   * chained turns, so one user message can span several turns; metrics are summed over them.
   */
  async function ask(sid, text, { maxClarifications = 2 } = {}) {
    const t0 = Date.now();
    const parts = [];
    const shown = [];
    let clarifications = 0;
    let input = [{ type: 'user.message', content: text }];
    for (let hop = 0; hop < 8; hop++) {
      const created = await req('POST', `/sessions/${sid}/turns`, { stream: false, input });
      const turn = await waitTurn(sid, created.data.id, t0);
      const ev = await events(sid, turn.id);
      parts.push({ turn, ev });
      const st = turn.state;
      const flat = ev.map(x => x.event ?? x);
      const callsById = new Map(flat.filter(e => e.type === 'model.message').flatMap(e => (e.tool_calls ?? []).map(c => [c.id, c])));
      // A paused turn names its open actions by event id; a done turn may still carry required_actions
      // (ask_user_question ends a turn as done with a tool.response_required). Both count as open.
      const openIds = new Set((st.action_required_on_events ?? []).map(a => a.id));
      const open = [...flat.filter(e => openIds.has(e.id)), ...(st.required_actions ?? [])];
      shown.push(visibleText(st, flat, callsById, open));
      if (!['paused', 'done'].includes(st.status) || !open.length) break;

      const next = [];
      for (const a of open) for (const ref of a.tool_calls ?? []) {
        const c = callsById.get(ref.id) ?? ref;
        const name = c.function?.name ?? c.name;
        if (a.type === 'tool.approval_required') {
          const d = approvalFor(name, c.function?.arguments); // no policy hook: nothing can allow a write
          parts.at(-1).approvals = [...(parts.at(-1).approvals ?? []), { tool: name, status: d.status, why: d.why }];
          next.push({ type: 'user.tool_approval', thread_id: a.thread_id, tool_call_id: ref.id, approval: { status: 'deny', reason: d.why } });
        } else if (a.type === 'tool.response_required' && name === 'ask_user_question' && clarifications < maxClarifications) {
          clarifications++;
          next.push({ type: 'user.tool_response', thread_id: a.thread_id, tool_call_id: ref.id, content: CLARIFY_REPLY });
        }
      }
      if (!next.length) break; // mcp auth, other client tools, or clarification budget spent
      input = next;
    }
    const last = parts.at(-1).turn;
    const metrics = parts.reduce((m, { turn }) => {
      const x = turn.state.metrics ?? {};
      return { tokens: m.tokens + (x.total_tokens ?? 0), cost_usd: m.cost_usd + (x.total_cost_in_usd ?? 0) };
    }, { tokens: 0, cost_usd: 0 });
    const s = summarizeEvents(parts.flatMap(p => p.ev));
    return {
      status: last.state.status,
      error: last.state.message ?? null,
      text: shown.filter(Boolean).join('\n\n'),
      clarifications,
      approvals: parts.flatMap(p => p.approvals ?? []),
      ms: Date.now() - t0,
      ...metrics,
      ...s,
    };
  }

  return {
    createSession: async () => (await req('POST', '/sessions', direct ? { agent: { spec: direct.spec }, metadata: direct.metadata } : {})).data,
    ask,
    events,
  };
}
