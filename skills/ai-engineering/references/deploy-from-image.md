---
name: deploy-from-image
description: Deploy a workload from an image that already exists, with no build step — a public image such as redis or postgres, or one from the tenant's own registry. Also the path for notebooks, rstudio and ssh-servers. Read this when the user names an image rather than a repository.
---

There is no build here, which removes the largest source of failure and changes what the useful checks are. What goes wrong instead is the image not being reachable, or the workload not being configured the way the image expects.

Applies to `service`, `async-service` and `job`, and it is the only path for `notebook`, `rstudio` and `ssh-server`, which run images the platform provides rather than anything built from user code.

## Contents

- Confirming the image is reachable
- Configuration the image expects
- Deploying
- When it does not start

## Confirming the image is reachable

An image reference that the cluster cannot pull produces a workload that never starts, and the failure appears at pull time rather than at deploy time. The deployment itself will report success.

Check before deploying rather than after:

- **Public images** are usually fine, but registries increasingly require authentication even for images that were previously anonymous. A `401` from a registry is the registry's decision, not a platform fault — report it rather than retrying.
- **Private images** need registry credentials configured in the tenant. If the image is in the tenant's own registry, the cluster's default registry usually already has access; `get_cluster` shows which registry that is.
- **Tags matter.** `latest` will pull whatever is current at the moment each pod starts, which means two replicas can end up running different code. Prefer a specific tag, and mention this if the user asks for `latest`.

## Configuration the image expects

An image built by someone else has expectations that are not visible in the image reference, and getting these wrong produces a container that starts and immediately exits — which reads as a crashloop rather than as a configuration problem.

Ask the user rather than assuming:

- **The port the application listens on.** This has to match what the image actually serves; a service exposing the wrong port produces a workload that looks healthy and answers nothing.
- **Environment variables and secrets.** Databases in particular refuse to start without them — `postgres` needs a password variable set, for instance. Secrets are referenced by FQN, not pasted as values.
- **Persistence.** A database deployed without a volume loses its data whenever the pod is replaced. If the user is deploying something stateful, raise this before deploying rather than after they lose data.
- **Resources.** An image with no limits set can be scheduled somewhere it cannot actually run.

## Deploying

1. Call `get_manifest_json_schema` for the entity type.
2. Collect the configuration above with `ask_user_question`. Do not choose ports or resource limits on the user's behalf.
3. Validate, then apply with `apply_manifest`. There is no local-build exception here — nothing is being built, so this always goes through the approval-gated tool.
4. Confirm the workload is actually running. The deployment reporting success means the rollout was accepted, not that the image pulled or that the container stayed up.

## When it does not start

The failure is almost always one of three things, and they are distinguishable:

**The image could not be pulled.** The container never ran, so there are no logs at all. The evidence is in events — `list_application_events`, or `list_k8s_events` for the live cluster view. Look for a pull failure naming the image.

**The container started and exited.** Usually a missing environment variable or a bad command. The logs exist but belong to the *previous* container, since the current attempt has not produced anything yet — read them with `previous: true`.

**Nothing will schedule it.** The pod sits `Pending` and reports no failure at all. Resource requests that no node can satisfy are the common cause.

`troubleshooting.md` covers all three in more detail, including why an empty result here is not evidence that the workload is healthy.
