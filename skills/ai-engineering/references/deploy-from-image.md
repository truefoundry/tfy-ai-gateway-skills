---
name: deploy-from-image
description: Deploy a workload from an image that already exists, with no build step — a public image, or one from the tenant's own registry. Read this when the user names an image rather than a repository.
---

There is no build, which removes the largest source of failure and changes what needs checking. What goes wrong instead is the image not being pullable, or the workload not being configured the way the image expects.

Applies to `service`, `async-service` and `job`.

## Contents
- Phase 1: Confirm the image is reachable
- Phase 2: Collect the configuration the image expects
- Phase 3: Validate and apply
- Manifest structure
- Diagnosing a workload that will not start
- Checklist

## Phase 1: Confirm the image is reachable

An image the cluster cannot pull produces a workload that never starts, and the deployment still reports success. Check before deploying.

- **Public images** — usually pullable, but registries increasingly require authentication for images that were previously anonymous. A `401` is the registry's access decision, not a platform fault. Report it; do NOT retry the same call.
- **Private images** — need registry credentials configured in the tenant. Call `get_cluster` to see the cluster's default registry, which images in the tenant's own registry are usually pullable from.
- **Tags** — `latest` resolves at each pod start, so two replicas can run different code. Prefer a specific tag, and say so if the user asks for `latest`.
- **Verifying** — ask the user which registry the image lives in, or read the registry directly. Do not assume an image is pullable because its name looks familiar.

## Phase 2: Collect the configuration the image expects

An image built by someone else has expectations that are invisible in its reference. Getting them wrong produces a container that starts and immediately exits, which reads as a crashloop rather than as misconfiguration.

**First, check whether the name is taken** — call `list_applications` filtered by it. If something is already deployed under that name you are updating, and the values below come from the deployed manifest rather than from the user. Read **Creating or updating** in `deploy-common.md` before going further.

Otherwise use `ask_user_question` for each of these — do NOT choose on the user's behalf:

| Input | Why it cannot be guessed |
|---|---|
| Port | Must match what the image actually serves. A service on the wrong port looks healthy and answers nothing. |
| Environment variables | Databases refuse to start without them — `postgres` needs a password variable set. |
| Secrets | Referenced by FQN (`tfy-secret://...`), never pasted as literal values. |
| Persistence | A stateful image with no volume loses its data when the pod is replaced. Raise this before deploying, not after. |
| Resources | Requests no node can satisfy leave the pod `Pending` forever with no error. |

Also call `list_workspaces` and take `workspace_fqn` from the response rather than constructing it. If it returns nothing for the workspace the user named, see **Resolving the workspace** in `deploy-common.md`.

## Phase 3: Validate and apply

Build the manifest as JSON → `validate_manifest` → fix and re-validate until it passes → `apply_manifest`.

Nothing is built here, so there is no local source and no reason to use the CLI — this always goes through `apply_manifest`.

After applying, confirm the workload is running. A successful apply means the rollout was accepted, not that the image pulled or that the container stayed up.

## Manifest structure

```yaml
type: service                          # or async-service, job
name: <application-name>
workspace_fqn: <fqn from list_workspaces>
image:
  type: image
  image_uri: redis:7.2                 # prefer a specific tag over `latest`
ports:
  - port: 6379
    protocol: TCP
    expose: false
resources:
  cpu_request: 0.2
  cpu_limit: 0.5
  memory_request: 500
  memory_limit: 1000
env:
  REDIS_PASSWORD: tfy-secret://<owner>:<secret-group>:<key>
```

## Diagnosing a workload that will not start

Start with `list_k8s_pods` and read the pod's `phase` and `problem`, then follow `troubleshooting.md`. Do not start from logs: whether logs exist at all is what the pod state tells you, and the three failure modes here are distinguished by that field rather than by what the logs contain.

The ones specific to deploying an image: `ImagePullBackOff` means the registry refused or the tag is wrong, so the container never ran and there is nothing to read. `CrashLoopBackOff` on a first deploy is usually a missing environment variable or a command the image does not expect. `Pending` means the resource requests cannot be satisfied by any node.

## Checklist

- [ ] For a user-supplied image, did I confirm it is pullable before deploying rather than after it failed?
- [ ] If a registry returned `401`, did I report it instead of retrying?
- [ ] Did I use a specific tag, or tell the user why `latest` is risky?
- [ ] Did I ask the user for the port rather than assuming the image's default?
- [ ] Did I ask which environment variables and secrets the image requires?
- [ ] For a stateful image, did I raise persistence before deploying?
- [ ] Did I take `workspace_fqn` from `list_workspaces` instead of constructing it?
- [ ] Are secrets referenced by FQN rather than pasted as values?
- [ ] Did I confirm the pods are running, rather than reporting success when apply returned?

For more info: `search_docs` with "deploy a prebuilt image", "introduction to a service".
