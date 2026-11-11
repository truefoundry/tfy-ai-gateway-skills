---
name: notebook-ssh
description: Deploy and debug workbench applications — notebook, codeserver, rstudio, spark-notebook and ssh-server — schema authoring, OAuth/login access, and runtime failures. Read before creating or fixing interactive IDE-style apps.
---

Workbench types are `notebook`, `codeserver`, `rstudio`, `spark-notebook` and `ssh-server` — first-class application types, **not** generic `service` manifests with Jupyter bolted on. `rstudio` can be disabled on an installation, in which case apply fails.

## Contents
- Author a new workbench
- Auth and URL access
- Runtime debugging
- Checklist

## Author a new workbench

1. `list_workspaces(name=<workspace>)` — take `fqn` (see **Resolving the workspace** in `deploy-common.md`).
2. In one parallel batch: `list_applications(applicationName=<name>, workspaceFqn=<fqn>)` (a row means you are updating — see `deploy-common.md`) and `get_manifest_json_schema` for the exact type.
3. Required: `name`, `workspace_fqn`, `image.image_uri`, `home_directory_size` (GB, default 20, 5–64000) and, for `ssh-server`, `ssh_public_key`. Ask the user for the image (no tool lists the platform's default workbench images) and, for SSH, their public key. `cull_timeout` is minutes of inactivity (notebook default 30, min 5). `validate_manifest` does not fill defaults, so write `home_directory_size` even when using 20.
4. The home directory is already persistent; attach volumes only for shared or extra data. If the volume application does not exist yet, author it from `get_manifest_json_schema` + `search_docs` for `volume`.
5. `validate_manifest` → `apply_manifest` (approval).
6. Return the links per `deployment-links.md`: the console link and, for every type except `ssh-server`, the URL from `list_applications` → `activeDeployment.metadata.endpoints`. Do not invent hostnames.

For "explore this dataset" requests: create/attach storage, then a notebook — not a one-off job unless they asked for batch.

## Auth and URL access

Interactive apps typically require **platform login / OAuth** in the browser. Raw `curl` to the notebook URL often fails with redirects or 401 even when the pod is Ready.

- Tell the user to open the endpoint while logged in to TrueFoundry.
- SSH-server: use the documented SSH command / key flow from docs or the deployment UI fields — do not invent bastion hosts.
- If login loops or OAuth errors: check workspace membership/RBAC, IdP config (cluster/tenant admin), and that the pod is Ready (`troubleshooting.md`).

## Runtime debugging

Same pod tooling as services, starting from `get_application_state`:

- Pending / GPU → `failure-modes/pending-scheduling.md`
- Image pull → `failure-modes/image-pull.md`
- Crash / OOM → `failure-modes/crashloop-oom-probes.md`
- Volume mount → `failure-modes/volumes-storage.md`
- Stuck rollout → `failure-modes/rollout-argocd.md`

User code errors inside Jupyter are **not** platform CrashLoops — read notebook cell output / kernel logs in the main container when the pod is Ready.

## Checklist

- [ ] Did I use the workbench type's schema (not `service`)?
- [ ] Did I set `image.image_uri`, `home_directory_size` and, for SSH, `ssh_public_key` from the user rather than guessing?
- [ ] Did I explain OAuth/browser login for URL access?
- [ ] Did I print the console link, and the workbench URL from `list_applications`, per `deployment-links.md`?
- [ ] For failures, did I reuse shared failure-mode playbooks?

For more info: `search_docs` with "notebook", "ssh server", "rstudio".
