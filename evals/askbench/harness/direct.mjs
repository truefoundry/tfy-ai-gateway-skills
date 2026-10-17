// direct.mjs — rebuilds the request the platform API sends to the agent runtime for an Ask TFY session,
// so a run can use the same agent with one input changed: the skills git url/ref (and optionally the model).
//
// The spec is taken from a live platform-created session on every run, never from a copy: the prompt and
// the tool policy belong to the product, and a stale copy would make the benchmark drift from what users
// get. Only the pieces the runtime reads from request headers are rebuilt here (MCP servers, skills mount,
// model, metadata); if the product changes them, update this file.

/** Header values are latin-1, so escape everything above 0x7e. */
export const toHeaderJson = v => JSON.stringify(v).replace(/[\u007f-￿]/g, c => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);

export const SKILL_NAME = 'tfy-platform-skills';
export const SKILL_DESCRIPTION =
  'Answer questions about TrueFoundry, an enterprise AI platform. Covers two products — AI Gateway ' +
  '(LLM proxy, MCP servers, agents, governance) and AI Engineering (deploy services, jobs, notebooks, ' +
  'workflows; ML repos, model registry, fine-tuning). Triggers on TrueFoundry, tfy CLI, Gateway ' +
  "entities/policies, tracing/observability, prompt management, or deploying applications — even " +
  "when the product name isn't stated.";
export const UPSTREAM_SKILLS = { url: 'https://github.com/truefoundry/tfy-ai-gateway-skills', ref: 'platform', path: 'skills' };

const MCP = {
  'tfy-platform-mcp': { url: o => `${o}/api/svc/truefoundry/mcp`, userAuth: true, description: 'Live TrueFoundry platform APIs for the signed-in user — clusters, workspaces, applications, MCP servers, gateway config, and related control-plane resources.\n' },
  'tfy-docs-mcp': { url: () => 'https://docs-mcp.truefoundry.com/docs-mcp/', userAuth: false, description: 'Search TrueFoundry product documentation (AI Gateway and AI Engineering).\n' },
};

/** sfs's NameSchema mapping for the inline model name. */
export function configuredName(modelName) {
  let n = modelName.toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/-+/g, '-').replace(/^-+|-+$/g, '');
  if (!n) n = 'model';
  if (!/^[a-z]/.test(n)) n = `m-${n}`;
  if (n.length === 1) n = `${n}0`;
  n = n.slice(0, 64).replace(/[^a-z0-9]+$/, '');
  return n.length < 2 ? `${n}0`.padEnd(2, '0') : n;
}

/**
 * The direct-mode agent: `template` is the agent object of a live platform-created session (spec +
 * metadata); `skills` overrides the skills mount and `model` the gateway model. Nothing else in the live
 * spec changes. MCP servers the live spec names that are not built in (an install-specific one) come from
 * `extraMcp`: {name: {url, description?, auth?}}.
 * Returns {spec, headers, metadata} for makeClient({direct}).
 */
export function buildDirect({ origin, key, template, skills = UPSTREAM_SKILLS, model, extraMcp = {}, tenant = 'truefoundry', application = 'ask_ai_bench' }) {
  const live = template.metadata?.modelIdentifier;
  if (!live?.includes('/')) throw new Error('direct: template session has no modelIdentifier metadata');
  const liveName = configuredName(live.slice(live.lastIndexOf('/') + 1));
  if (template.agent.spec.model?.name !== `tfy-gateway/${liveName}`) throw new Error(`direct: spec model ${template.agent.spec.model?.name} does not match ${live}`);
  // `model` swaps the gateway model and nothing else in the live spec.
  const modelId = model ?? live;
  if (!modelId.includes('/')) throw new Error(`direct: model ${modelId} must be <provider-account>/<model>`);
  const name = configuredName(modelId.slice(modelId.lastIndexOf('/') + 1));
  const spec = { ...template.agent.spec, model: { ...template.agent.spec.model, name: `tfy-gateway/${name}` } };
  const mcp = Object.fromEntries(spec.mcp_servers.map(({ name: n }) => {
    const m = MCP[n];
    if (m) return [n, { url: m.url(origin), description: m.description, ...(m.userAuth ? { auth: { type: 'header', headers: { Authorization: `Bearer ${key}` } } } : {}) }];
    const x = extraMcp[n];
    if (!x?.url) throw new Error(`direct: MCP server ${n} is in the live spec but unknown here; pass it in ASKBENCH_MCP_EXTRA as {"${n}":{"url":"..."}}`);
    return [n, { url: x.url, description: x.description ?? '', ...(x.auth ? { auth: x.auth } : {}) }];
  }));
  const headers = {
    'x-tfg-mcp': toHeaderJson(mcp),
    'x-tfg-skills': toHeaderJson({ [SKILL_NAME]: { url: skills.url, ref: skills.ref, path: skills.path ?? 'skills', description: SKILL_DESCRIPTION } }),
    'x-tfg-models': toHeaderJson({ 'tfy-gateway': { base_url: `${origin}/api/llm/api/inference/openai`, auth: { api_key: key }, models: [{ model_id: modelId, name, properties: {} }] } }),
    'x-tfy-metadata': toHeaderJson({ tenant_name: tenant, application }),
  };
  return { spec, headers, metadata: { application, modelIdentifier: modelId, skills_ref: `${skills.url}@${skills.ref}` } };
}
