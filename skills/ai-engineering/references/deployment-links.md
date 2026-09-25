---
name: deployment-links
description: After any AI Engineering deploy or update, print the TrueFoundry UI link and (when applicable) the live service/notebook endpoint. Read at the end of every successful apply_manifest / tfy deploy — never leave the user without a clickable link.
---

Every successful deploy must end with **real links**, not “it’s deployed.” Never invent hostnames or guess path shapes.

## Contents
- Console (UI) link — always
- Service / async-service HTTP endpoint
- Notebook / RStudio / SSH
- Jobs, Helm, volumes
- What to print
- Checklist

## Console (UI) link — always

Every application type has a deployments page:

1. Resolve `applicationId` from `apply_manifest` / `get_application` / `list_applications` (the app’s `id` — not the deployment id alone).
2. Resolve `controlPlaneUrl` from `get_me` (never hardcode or leave `{controlPlaneUrl}`).
3. Print:

```
{controlPlaneUrl}/deployments/{applicationId}
```

Optional useful tabs (append as needed): `?tab=pods`, `?tab=logs`, `?tab=deployments`, `?tab=readme`.

This is the **primary** link for every deploy — service, job, notebook, helm, model, volume.

## Service / async-service HTTP endpoint

For workloads meant to be called over HTTP (including model servers):

1. Call `generate_deployment_endpoint` with:
   - `applicationType`: `service` or `async-service`
   - `workspaceId`: workspace `id` (from `list_workspaces`)
   - `applicationName`: application name
   - `port`: the exposed port from the manifest when relevant
2. Build the URL from the response:
   - Wildcard base domain → `https://{host}` (host already includes the slug)
   - Non-wildcard → `https://{host}{path}`
3. If the tool errors (no base domain, unsupported type), say so and still give the **console** link. Do not invent a host from the workspace name.

For OpenAI-compatible model servers, also show the useful paths, e.g. `https://{host}/v1/models`, `.../v1/chat/completions` (or embeddings/rerank as appropriate) — after the base endpoint is known.

Auth: if the service requires platform auth, note that browser/API calls may need login or tokens — do not pretend the URL is anonymously open.

## Notebook / RStudio / SSH

- **Notebook / RStudio:** console link **plus** the workbench URL from the deployment / `generate_deployment_endpoint` equivalent or fields returned on the application/deployment. Tell the user to open it while logged into TrueFoundry (`notebook-ssh.md`).
- **SSH server:** console link **plus** the documented SSH command / host from the deployment UI fields — do not invent bastions.

## Jobs, Helm, volumes

| Type | Links to print |
|---|---|
| `job` / cron | Console link (runs/pods live there). No HTTP endpoint unless the job somehow exposes one. |
| `helm` | Console link. Chart may expose its own ingress — only quote hosts that come from applied resources / docs, not guesses. |
| `volume` | Console link. No service endpoint. |
| Model (`service` with model server) | Console + `generate_deployment_endpoint` (+ smoke path). See `model-deploy.md`. |

## What to print

After apply + a quick health check (`get_deployment` / pods when useful), end the reply with a short block, for example:

- **Application:** `https://<controlPlane>/deployments/<applicationId>`
- **Endpoint:** `https://<host>/` (services only)
- **Try:** `curl …` when a smoke call helps (models)

Substitute real values. Never leave placeholders.

## Checklist

- [ ] Did I fetch `controlPlaneUrl` via `get_me`?
- [ ] Did I use the real `applicationId` (not a guessed slug)?
- [ ] Did I print `{controlPlaneUrl}/deployments/{applicationId}`?
- [ ] For service/async-service/model, did I call `generate_deployment_endpoint` instead of inventing a host?
- [ ] If endpoint generation failed, did I still give the console link and explain why?

For more info: `search_docs` with "service endpoint", "deployments".
