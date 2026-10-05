---
name: deployment-links
description: After any AI Engineering deploy or update, print the TrueFoundry console link and, where the application has one, its real endpoint — taken from the deployed manifest or the application listing, never constructed. Read at the end of every successful apply_manifest / tfy deploy.
---

Every successful deploy ends with **real links**, not "it's deployed". Every value comes from a tool response. Never build a hostname from the application or workspace name.

## Contents
- Console link — always
- Service and async-service endpoint
- Notebook and RStudio URL
- SSH server, job, Helm, volume
- What to print
- Checklist

## Console link — always

Every application type has a page in the console:

```
{controlPlaneUrl}/deployments/{applicationId}
```

- `controlPlaneUrl` comes from `get_me`.
- `applicationId` is the application's `id` from the `apply_manifest` response or `get_application` — not the deployment id.

## Service and async-service endpoint

The URL is in the deployed manifest. Read `ports` from the `activeDeployment.manifest` that `get_application` returns:

- A port with `expose: true` is reachable at `https://{host}{path}`, using that port's `host` and `path`. A `path` always ends in `/`; use `/` when it is not set.
- No exposed port means no public endpoint. Say so rather than producing one.

This covers model servers too: catalogue specs from `get_model_deployment_specs` already carry `ports[].host` when the cluster has a base domain, and set `expose: false` when it does not.

For OpenAI-compatible model servers, also show the routes the server answers on, appended to that URL: `v1/models`, `v1/chat/completions` (or the embeddings / rerank route).

If the port has `auth` configured, say that requests need credentials — do not present the URL as open.

`generate_deployment_endpoint` is not how you read an endpoint. It **suggests** a `host` (and `path`) for a manifest you are building — see **Exposing a port** in `deploy-common.md`.

## Notebook and RStudio URL

These have no `ports` in the manifest. The URL is added to the **listing**, not to `get_application`:

1. `list_applications` filtered by the name, and take the row in the right workspace.
2. Read `activeDeployment.metadata.endpoints` — each entry has `host` and `path`. The URL is `https://{host}{path}`.

If `endpoints` is missing or the host is empty, give the console link and say the workbench URL was not available. Tell the user to open it while logged in to TrueFoundry — `notebook-ssh.md` covers access.

## SSH server, job, Helm, volume

| Type | What to print |
|---|---|
| `ssh-server` | Console link. Take the connection details from the console or `search_docs` ("ssh server"); do not construct a host or command. |
| `job` | Console link — runs and their pods are there. |
| `helm` | Console link. Quote a chart's ingress host only if it appears in `get_application_argocd_resources` or `get_applied_k8s_manifest`. |
| `volume` | Console link. |

## What to print

After the apply and a basic health check, end the reply with real values in this shape:

- **Application:** the console link
- **Endpoint:** the service, model or notebook URL, when there is one
- **Try:** a `curl` against a model route, when a smoke call helps

## Checklist

- [ ] Did I take `controlPlaneUrl` from `get_me` and the application `id` from a tool response?
- [ ] For a service or model, did I read `ports[].host` / `path` from the deployed manifest — and say so when nothing is exposed?
- [ ] For a notebook or RStudio, did I read `activeDeployment.metadata.endpoints` from `list_applications`?
- [ ] Is every host in my reply from a tool response, none constructed?

For more info: `search_docs` with "service endpoint", "deployments".
