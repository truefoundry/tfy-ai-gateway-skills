---
name: image-pull
description: ImagePullBackOff, ErrImagePull, registry auth failures, wrong tag/digest, private registry credentials. Read when pods never start and reason is ImagePullBackOff or ErrImagePull, or events with reason Failed or BackOff mention pulling the image.
---

If the image cannot be pulled, the container never runs. There are **no application logs**. Looking at `get_logs` and reporting silence is a misdiagnosis.

## Triage

1. Confirm container `reason: ImagePullBackOff` or `ErrImagePull` in `get_application_state`.
2. `list_application_events` — pull failures have reason `Failed` or `BackOff`; the message usually includes registry host, tag, and auth error text.
3. From `get_application` / `get_deployment`, read the image URI the deploy is trying to use (manifest `image` or build `imageUri`; the container's `image` in `get_application_state` shows it too).
4. `get_cluster` → `manifest.default_registry_fqn` when the image is private.

Steps 2–4 are independent: issue them in one message.

## Message → cause

| Event / message pattern | Cause | What to tell the user |
|---|---|---|
| `manifest unknown` / `not found` | Tag or digest does not exist | Fix tag; confirm the build actually produced `imageUri` |
| `unauthorized` / `denied` / `authentication required` | Missing or wrong pull credentials | Cluster/workspace image pull secret / registry integration |
| `x509` / TLS errors | Corporate MITM or bad registry cert | Infra/registry TLS — outside app manifest |
| timeout / i/o / dial | Network path from nodes to registry | Network policy, NAT, private endpoint |
| Build succeeded but pull fails on a digest that never existed in *this* registry | Image pushed elsewhere; wrong registry host in URI | Compare build `imageUri` host to where nodes can pull |

## Build vs pull

- **No `imageUri` on the build** → build never produced an image. Go to `builds.md`. Do not stay in ImagePull.
- **Build `SUCCEEDED` with `imageUri`, pull fails** → pure registry/auth/tag problem on the cluster side.
- **Deduped/reused build** → URI is old but valid; pull failures are still registry/auth unless the registry GC deleted the tag.

## Private registries

TrueFoundry clusters typically use a configured Docker registry integration. If pull secrets are wrong after a registry rotation, every new pod in the workspace can fail together — check whether **other** apps in the same workspace pull successfully. If they do, the URI/tag for this app is wrong; if they do not, fix cluster/workspace registry config (may need a human with cluster admin).

Do not ask for registry passwords in chat. Point at the integration / pull secret configuration in the product and docs.

## Checklist

- [ ] Did I avoid concluding from empty application logs?
- [ ] Did I read the pull error message from events?
- [ ] Did I confirm an `imageUri` exists from the build/deploy?
- [ ] Did I distinguish "tag missing" from "auth denied" from "network"?

For more info: `search_docs` with "docker registry", "image pull", "private registry".
