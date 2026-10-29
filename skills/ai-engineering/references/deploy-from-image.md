---
name: deploy-from-image
description: Deploy a workload from an image that already exists, with no build step — a public image, or one from the tenant's own registry. Read this when the user names an image rather than a repository.
---

There is no build, which removes the largest source of failure and changes what needs checking. What goes wrong instead is the image not being pullable, or the workload not being configured the way the image expects.

Applies to `service`, `async-service` and `job`. Read `deploy-common.md` alongside this.

## Contents
- Phase 1: Confirm the image is reachable
- Phase 2: Collect the configuration the image expects
- Phase 3: Validate and apply
- Manifest structure
- Diagnosing a workload that will not start
- Checklist

## Phase 1: Confirm the image is reachable

An image the cluster cannot pull produces a workload that never starts, and the deployment still reports success. Check before deploying.

- **Private image** — set `image.docker_registry` to the registry integration FQN. Without it no pull credentials are attached and the pull fails with `ImagePullBackOff`. If the image lives in the cluster's default registry, use `default_registry_fqn` from `get_cluster`; otherwise ask the user for the registry FQN.
- **Public image** — if the shell has `docker`, run `docker manifest inspect <image>` to confirm it is pullable; otherwise tell the user it is unverified. Registries increasingly require authentication for images that were previously anonymous; a `401` is the registry's access decision, not a platform fault. Report it; do not retry the same call.
- **Tags** — `latest` resolves at each pod start, so two replicas can run different code. Prefer a specific tag, and say so if the user asks for `latest`.

Do not assume an image is pullable because its name looks familiar.

## Phase 2: Collect the configuration the image expects

An image built by someone else has expectations that are invisible in its reference. Getting them wrong produces a container that starts and immediately exits, which reads as a crashloop rather than as misconfiguration.

1. `list_workspaces(name=<workspace>)` — keep `fqn` and `id` (see **Resolving the workspace** in `deploy-common.md`).
2. In one parallel batch: `list_applications(applicationName=<name>, workspaceFqn=<fqn>)` and `get_manifest_json_schema` for the type. A row back means you are updating — read **Creating or updating** in `deploy-common.md`, and take the values below from the deployed manifest rather than from the user.
3. Otherwise use `ask_user_question` for each of these — do not choose on the user's behalf:

| Input | Why it cannot be guessed |
|---|---|
| Port, and whether to expose it | Must match what the image actually serves. A service on the wrong port looks healthy and answers nothing. An exposed port needs a `host` — see **Exposing a port** in `deploy-common.md`. |
| Environment variables | Databases refuse to start without them — `postgres` needs a password variable set. |
| Secrets | Referenced as `tfy-secret://<tenant>:<group>:<key>` (see `secrets.md`), never pasted as literal values. |
| Persistence | A stateful image with no volume loses its data when the pod is replaced. Raise this before deploying, not after. |
| Resources | Requests no node can satisfy leave the pod `Pending` forever with no error. |

## Phase 3: Validate and apply

Build the manifest as JSON → `validate_manifest` → fix and re-validate until it passes → `apply_manifest`. Nothing is built, so there is no local source and no reason to use the CLI.

After applying, confirm the workload is running. A successful apply means the rollout was accepted, not that the image pulled or that the container stayed up. Then print the links in `deployment-links.md`.

## Manifest structure

```yaml
type: service                          # job / async-service: see below
name: <application-name>
workspace_fqn: <fqn from list_workspaces>
replicas: 1
image:
  type: image
  image_uri: redis:7.2                 # prefer a specific tag over `latest`
  # docker_registry: <registry integration FQN>   # required for a private image
ports:
  - port: 6379
    protocol: TCP
    expose: false
resources:
  cpu_request: 0.2
  cpu_limit: 0.5
  memory_request: 500
  memory_limit: 1000
  ephemeral_storage_request: 1000
  ephemeral_storage_limit: 2000
env:
  REDIS_PASSWORD: tfy-secret://<tenant>:<secret-group>:<key>
```

- `job`: drop `ports` and `replicas`; add `trigger: {type: manual}` (or `{type: scheduled, schedule: "<cron>"}`) and optionally `retries` (0–10).
- `async-service`: `worker_config` is required; take its shape from `get_manifest_json_schema`.

## Diagnosing a workload that will not start

Start with `get_application_state` and read the pod `status` and container `reason`, then follow `troubleshooting.md`. Do not start from logs: whether logs exist at all is what the pod state tells you, and the three failure modes here are distinguished by that field rather than by what the logs contain.

The ones specific to deploying an image: `ImagePullBackOff` means the registry refused, the tag is wrong, or `docker_registry` is missing for a private image, so the container never ran and there is nothing to read. `CrashLoopBackOff` on a first deploy is usually a missing environment variable or a command the image does not expect. `Pending` means the resource requests cannot be satisfied by any node.

## Checklist

- [ ] For a private image, did I set `image.docker_registry`? For a public one, did I check it or say it is unverified?
- [ ] If a registry returned `401`, did I report it instead of retrying?
- [ ] Did I use a specific tag, or tell the user why `latest` is risky?
- [ ] Did I ask the user for the port, environment variables and secrets rather than assuming the image's defaults?
- [ ] For a stateful image, did I raise persistence before deploying?
- [ ] Did I take `workspace_fqn` from `list_workspaces` and write every required field?
- [ ] Are secrets referenced as `tfy-secret://...` rather than pasted as values?
- [ ] Did I confirm the pods are running, rather than reporting success when apply returned?
- [ ] Did I print the links per `deployment-links.md`?

For more info: `search_docs` with "deploy a prebuilt image", "introduction to a service".
