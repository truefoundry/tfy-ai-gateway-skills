---
name: notebook-ssh
description: Deploy and debug notebook, rstudio, and ssh-server applications — schema authoring, OAuth/login access, and runtime failures. Read before creating or fixing interactive IDE-style apps.
---

`notebook`, `rstudio`, and `ssh-server` are first-class application types — **not** generic `service` manifests with Jupyter bolted on.

## Contents
- Author a new notebook / SSH / RStudio
- Auth and URL access
- Runtime debugging
- Checklist

## Author a new notebook / SSH / RStudio

1. Resolve workspace FQN (`list_workspaces`).
2. `get_manifest_json_schema` for the exact type: `notebook` | `rstudio` | `ssh-server`.
3. Fill required fields (name, workspace_fqn, resources, image if configurable). Prefer platform defaults for Jupyter images unless the user specified one.
4. Attach volumes/datasets via documented volume mounts when they need persistent home or data. If the volume application does not exist yet, author it from `get_manifest_json_schema` + `search_docs` for `volume` (no dedicated playbook).
5. `validate_manifest` → `apply_manifest` (approval).
6. Return links per `deployment-links.md`: console `{controlPlaneUrl}/deployments/{applicationId}` **and** the notebook/SSH endpoint — do not invent hostnames.

For “explore this dataset” requests: create/attach storage, then notebook — not a one-off job unless they asked for batch.

## Auth and URL access

Interactive apps typically require **platform login / OAuth** in the browser. Raw `curl` to the notebook URL often fails with redirects or 401 even when the pod is Ready.

- Tell the user to open the endpoint while logged into TrueFoundry.
- SSH-server: use the documented SSH command / key flow from docs or the deployment UI fields — do not invent bastion hosts.
- If login loops or OAuth errors: check workspace membership/RBAC, IdP config (cluster/tenant admin), and that the pod is Ready (`troubleshooting.md`).

## Runtime debugging

Same pod tooling as services:

- Pending / GPU → `failure-modes/pending-scheduling.md`
- Image pull → `failure-modes/image-pull.md`
- Crash / OOM → `failure-modes/crashloop-oom-probes.md`
- Volume mount → `failure-modes/volumes-storage.md`
- Stuck rollout → `failure-modes/rollout-argocd.md`

User code errors inside Jupyter are **not** platform CrashLoops — read notebook cell output / kernel logs in the main container when the pod is Ready.

## Checklist

- [ ] Did I use the notebook/rstudio/ssh-server schema (not `service`)?
- [ ] Did I explain OAuth/browser login for URL access?
- [ ] Did I return the real endpoint after apply?
- [ ] Did I print the console link per `deployment-links.md`?
- [ ] For failures, did I reuse shared failure-mode playbooks?

For more info: `search_docs` with "notebook", "ssh server", "rstudio".
