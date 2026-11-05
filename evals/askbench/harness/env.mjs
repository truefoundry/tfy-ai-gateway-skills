// env.mjs — where the benchmark talks to, and the redaction applied to everything it writes to disk.

/** Reads ASKBENCH_TFY_HOST / ASKBENCH_TFY_API_KEY; the host may be given with or without a path. */
export function env(e = process.env) {
  const host = e.ASKBENCH_TFY_HOST, key = e.ASKBENCH_TFY_API_KEY;
  if (!host || !key) throw new Error('missing ASKBENCH_TFY_HOST / ASKBENCH_TFY_API_KEY');
  const origin = new URL(/^https?:\/\//.test(host) ? host : `https://${host}`).origin;
  return { origin, key, tenant: e.ASKBENCH_TFY_TENANT || 'truefoundry' };
}

const R = '<redacted>';
const JWT = /eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*/g;
const TFY_KEY = /\btfy[-_][A-Za-z0-9_-]{32,}/g;
const BEARER = /\bBearer\s+[A-Za-z0-9._~+/=-]{16,}/gi;
const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/g;
const SECRET_FIELD = /(token|api_?key|apikey|secret|password|authorization)$/i;

/** The strings that must never reach disk: the key, the control-plane origin and its host name. */
export const secretsOf = ({ origin, key }) => [key, origin, origin && new URL(origin).host].filter(Boolean);

/**
 * Scrubs every string in a JSON-like value: the given secrets (the key, the control-plane host), bearer
 * tokens, JWTs, tfy-* keys and email addresses. `secrets` is a string or a list of strings.
 */
export function redact(v, secrets = []) {
  if (typeof v === 'string') {
    let s = v;
    for (const x of [].concat(secrets).filter(Boolean)) s = s.split(x).join(R);
    return s.replace(JWT, R).replace(TFY_KEY, R).replace(BEARER, `Bearer ${R}`).replace(EMAIL, '<redacted-email>');
  }
  if (Array.isArray(v)) return v.map(x => redact(x, secrets));
  if (!v || typeof v !== 'object') return v;
  const out = {};
  for (const [k, x] of Object.entries(v)) out[k] = typeof x === 'string' && SECRET_FIELD.test(k) ? R : redact(x, secrets);
  return out;
}
