---
name: rollout-strategy
description: Explain and configure rolling update / canary / blue-green rollout strategy — surge and unavailable limits, the defaults the platform applies when none is set, and why an apply can briefly take the old pod down. Read when users ask about downtime on config changes, pods replaced after a replica edit, surge/unavailable, or want canary / blue-green / traffic splitting.
---

When an apply changes a service's pod template, the pods are replaced under its `rollout_strategy`. That is why a "small" edit can look like a full redeploy, and with 0% surge a single replica can go down before its replacement is Ready.

Take field names from `get_manifest_json_schema` for `service` / `async-service`.

## Contents
- When pods are replaced
- Rolling update (max surge / max unavailable)
- FAQ: we only changed replicas and the old pod went down
- Canary and blue-green
- Diagnose a bad rollout
- Checklist

## When pods are replaced

Every apply creates a new deployment version, but pods are replaced only when the pod template changes (image, env, resources, probes, labels). A replica-count or autoscaling-bounds edit usually leaves the template unchanged, so pods are scaled, not replaced. Exception: moving to or from `replicas: 1` on a CPU-only on-demand service in a production environment toggles a do-not-disrupt annotation, which changes the template and rolls pods.

Always start from the live manifest (**Creating or updating** in `deploy-common.md`).

## Rolling update (max surge / max unavailable)

`{type: rolling_update, max_surge_percentage, max_unavailable_percentage}` — write both percentages; `validate_manifest` lists them as required.

| Knob | Meaning |
|---|---|
| `max_surge_percentage` | How far **above** desired replica count new pods may go during the rollout |
| `max_unavailable_percentage` | How many pods (as % of desired) may be **down** during the rollout |

`max_surge_percentage` and `max_unavailable_percentage` cannot both be 0; apply rejects it.

If the manifest has no `rollout_strategy`, the platform still applies one: 0% surge / 25% unavailable, except CPU-only services in a production environment, which get 10% surge / 0% unavailable. Only NIM catalogue specs write `rollout_strategy` explicitly (0% / 25%). For GPU workloads where you cannot afford extra nodes, 0% surge with some unavailability is the usual choice.

Implications:

- **Surge 0%** → no extra new pod is brought up before an old one stops. With **1 replica**, the only pod can be terminated **before** the replacement is Ready → **downtime** (and a long model reload).
- **Unavailable 25%** with few replicas still rounds in ways that allow the sole replica to go down.
- **Surge > 0%** needs spare GPU/CPU capacity or the new pod stays Pending (`failure-modes/pending-scheduling.md`) while old pods may already be draining.

Recommended reading for users: https://www.truefoundry.com/docs/rollout-strategy

## FAQ: we only changed replicas and the old pod went down

**Symptom (production):** replica bounds changed (e.g. min/max from 1–2 to 2–3), a new ReplicaSet appeared, the existing pod went down, and traffic blipped until the new pod loaded.

1. Read `rollout_strategy` from the live manifest. If it is absent, the defaults above apply; absence does not mean there is no strategy.
2. Find out whether the pod template changed. In one parallel batch: `get_pod_template_hash_map`, `get_application_state` (pod `version` vs `activeVersion`) and `list_application_events`. To compare the two versions' manifests, use `list_application_deployments`. A replica-only edit normally scales; a new pod-template hash means something else changed too (or the `replicas: 1` exception above applies).
3. If the template did change and the strategy has 0% surge, say clearly that this is expected under that strategy, not a platform bug. For **single-replica GPU model servers**, the downtime equals schedule + image pull + **model download/load** (minutes to hours without cache).
4. Mitigations to propose (edit live manifest, validate, apply with approval):
   - Raise **`max_surge_percentage`** (e.g. 25–100%) **if** spare GPUs exist, so a new pod can become Ready before the old one stops.
   - Keep **`min_replicas` ≥ 2** in prod before risky applies, so unavailable % does not remove all capacity.
   - Use **canary** when they need traffic-controlled promotion (below).
   - Ensure the **model cache volume** works so replacement pods do not re-download weights (`model-serving-faq.md`, `failure-modes/volumes-storage.md`).
5. Verify with `get_application_state` and events — not from `DEPLOY_SUCCESS` alone.

Do not tell the user "replica changes never recreate pods", and do not skip reading their actual `rollout_strategy`.

## Canary and blue-green

- **Canary** — shift a traffic percentage to the new version in steps; pause/promote. Use when they need controlled production exposure.
- **Blue-green** — bring up the full new set, cut traffic over, then tear down the old one.

Skip both for a one-replica dev app, where a rolling update with sensible surge is enough.

Canary and blue-green are `service`-only (`async-service` allows only `rolling_update`) and need the Argo Rollouts addon; canary also routes traffic through Istio. Fields:

```yaml
rollout_strategy:
  type: canary
  steps:
    - weight_percentage: 20            # 0-100
      pause_duration: 300              # seconds; omit to pause until promoted
    - weight_percentage: 100
```

```yaml
rollout_strategy:
  type: blue_green
  enable_auto_promotion: false
  auto_promotion_seconds: 30
```

Apply rejects: `replicas` (or `min_replicas`) below 1 with canary/blue-green; `auto_shutdown` with canary/blue-green; `rolling_update` with both percentages 0.

To enable one:

1. Start from the live manifest (`deploy-common.md`) and add `rollout_strategy` as above.
2. Check the probes: failed probes abort progression (`failure-modes/crashloop-oom-probes.md`).
3. `validate_manifest` → explain the traffic steps → `apply_manifest` (approval).
4. Watch the new pods and smoke-test before calling it done. A canary that does not advance → `failure-modes/rollout-argocd.md`.

To roll back, call `redeploy_application(id=<applicationId>, deploymentId=<deployment to restore>)` after approval, taking the deployment id from `list_application_deployments`.

## Diagnose a bad rollout

| Observation | Next |
|---|---|
| New ReplicaSet, old pod terminating, surge 0% | Expected under strategy if the template changed — explain + mitigate |
| New pod Pending (GPU) while old already gone | Capacity (`failure-modes/pending-scheduling.md`) compounded by surge 0% |
| Rollout stuck / OutOfSync | `failure-modes/rollout-argocd.md` |
| Canary not advancing | Probes and Rollout state (`get_application_argocd_resources`, events) |

## Checklist

- [ ] Did I read the app's actual `rollout_strategy` — and apply the platform defaults when it is absent?
- [ ] For "pods replaced after a replica edit", did I check whether the pod template changed before explaining?
- [ ] For single-replica GPU models, did I warn about surge 0% downtime?
- [ ] Did I avoid 0/0 rolling percentages, and canary/blue-green on async-service or with `auto_shutdown`?
- [ ] Did I validate + apply strategy edits and rollbacks only with approval?

For more info: `search_docs` with "rollout strategy", "canary", "rolling update", "autoscaling".
