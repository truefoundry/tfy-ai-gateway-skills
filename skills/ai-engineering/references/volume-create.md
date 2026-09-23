---
name: volume-create
description: Create TrueFoundry volume applications and wire mounts into services, jobs, notebooks, and model caches. Read when the user needs a PVC, shared data volume, or model cache disk.
---

Volumes are their own application type (`volume`). Mount failures on other apps use `failure-modes/volumes-storage.md`; **creating** the volume is this file.

## Contents
- Create a volume
- Mount into an application
- Model cache sizing
- Checklist

## Create a volume

1. Resolve workspace FQN.
2. `get_manifest_json_schema` for `volume`.
3. Set name, workspace_fqn, size, storage class (must exist on the cluster — if Pending/FailedMount later, check storage class via cluster docs/addons).
4. `validate_manifest` → `apply_manifest` (approval).
5. Wait until the volume application is Ready / PVC bound before depending on it from another app.

If the cluster has no suitable storage class, stop and use `cluster-onboard.md` / `failure-modes/volumes-storage.md` — do not keep recreating volumes.

## Mount into an application

1. Fetch the **target** app’s live manifest.
2. Add the volume mount / volume reference fields per that app’s schema (`service`, `job`, `notebook`, …).
3. Full-replace rules apply (`deploy-common.md`).
4. Validate → apply → confirm mount in pod (`list_k8s_pods`, events).

## Model cache sizing

LLM weights are large. Undersized caches show up as download failures / `No space left`:

- Size from model card parameter count / Hub size (leave headroom).
- Put HF cache on the volume path the catalogue / downloader expects when you customize.
- Fixing size usually means recreate or expand per storage product capabilities — follow docs; say if online expand is unsupported.

## Checklist

- [ ] Did I author `type: volume` from schema before mounting?
- [ ] Did I confirm storage class / bind success before blaming the service?
- [ ] For models, did I size for weights + headroom?

For more info: `search_docs` with "volume", "persistent volume", "artifacts download".
