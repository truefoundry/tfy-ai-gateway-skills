---
name: networking
description: Service networking — endpoints, auth, SSL/custom domains, sticky sessions, and common connectivity failures. Read when users cannot reach a service, need HTTPS/custom domain, sticky routing, or CORS/auth issues.
---

TrueFoundry services expose HTTP(S) endpoints via the platform ingress. Most “it won’t connect” reports are endpoint URL mistakes, auth, or sticky/header misconfig — not cluster DNS bugs.

## Contents
- Resolve the endpoint
- Auth and CORS
- Sticky sessions
- SSL / custom domains
- Common failures
- Checklist

## Resolve the endpoint

1. Prefer `generate_deployment_endpoint` (or the endpoint on `get_application` / deployment) over guessing hostnames.
2. Confirm the **port** in the manifest matches what the process listens on (model servers often 8000/8080).
3. Path matters: vLLM/SGLang OpenAI routes live under `/v1/...`; hitting `/` may 404 even when healthy.

## Auth and CORS

- If the service or workspace enforces auth, unauthenticated curls fail with 401/403 — not a crash.
- Notebooks/SSH often use **OAuth / platform login** (`notebook-ssh.md`) — browser access differs from raw curl.
- CORS errors are browser-only; fix allowed origins in the service/ingress config per schema/docs, or call from server-side.

## Sticky sessions

Pin requests with the same session key to one replica (prefix cache for vLLM/SGLang):

1. On the service manifest `labels`, set `tfy_sticky_session_header_name` to a header name (e.g. `x-truefoundry-sticky-session-id`). Confirm via schema/docs if the field moves.
2. Clients must send that header with a stable value (conversation id / user id).
3. **Best-effort only** — pod eviction, scale-up/down, or node loss reshuffles sessions. Do not put critical state only in sticky routing.

See docs “sticky routing”. Combine with `autoscaling.md` carefully.

## SSL / custom domains

- Default platform endpoints usually already terminate TLS.
- Custom domains / certificates: follow `search_docs` for custom domain / SSL; requires cluster/ingress prerequisites — do not invent cert-manager YAML outside documented fields.
- If HTTPS fails but HTTP works (or vice versa), check whether the user is using the platform URL vs a custom host still propagating.

## Common failures

| Symptom | Check |
|---|---|
| DNS / connection refused | Endpoint host, service Ready pods, rollout stuck (`rollout-argocd.md`) |
| 401/403 | Auth headers, workspace policy, Gateway key vs service auth |
| 404 on `/v1/...` | Wrong base URL path; smoke `/v1/models` first |
| Works with 1 replica, flaky with N | Sticky header missing for prefix-cache workloads; or non-ready pods in Service |
| Timeout only after idle | Scale-to-0 cold start (`autoscaling.md`) — wait and retry |
| Gateway works, direct service fails (or reverse) | Gateway integration base URL vs raw service URL mismatch |

## Checklist

- [ ] Did I use `generate_deployment_endpoint` instead of inventing a host?
- [ ] Did I verify pods Ready before blaming networking?
- [ ] For sticky, did I set the label and tell the client the exact header?
- [ ] For custom domain/SSL, did I follow docs/schema rather than raw ingress manifests?

For more info: `search_docs` with "sticky routing", "custom domain", "service endpoint", "authentication".
