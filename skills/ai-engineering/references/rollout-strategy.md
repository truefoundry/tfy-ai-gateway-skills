---
name: rollout-strategy
description: Explain and configure rolling update / canary / blue-green rollout strategy — including why changing replica min/max can create a new ReplicaSet and briefly take the old pod down. Read when users ask about downtime on config changes, replica scaling behavior, surge/unavailable, or canary.
---

Any **manifest apply** that creates a new deployment revision (image, env, resources, **replicas / autoscaling min·max**, probes, …) is rolled out according to `rollout_strategy` on the service. That is why a “small” replica-count edit can look like a full redeploy: Kubernetes/Argo replaces pods under the configured surge and unavailable limits.

Confirm field names with `get_manifest_json_schema` for `service` / `async-service` and `search_docs` (“rollout strategy”).

## Contents
- When a new revision is created
- Rolling update (max surge / max unavailable)
- FAQ: we only changed replicas and the old pod went down
- Canary and blue-green
- Diagnose a bad rollout
- Checklist

## When a new revision is created

Editing the live manifest and applying (including only `replicas` or autoscaling `min`/`max`) produces a **new revision**. Expect:

- A new ReplicaSet / Rollout revision in the cluster
- Pods replaced according to `rollout_strategy` — not an in-place “HPA-only” tweak outside a revision (unless the product path you used is pure scale without a new deploy — verify with `get_deployment` / applied manifest)

Always start from `activeDeployment.manifest` (`deploy-common.md`).

## Rolling update (max surge / max unavailable)

Rolling update swaps old pods for new ones gradually:

| Knob | Meaning |
|---|---|
| `max_surge_percentage` | How far **above** desired replica count new pods may go during the rollout |
| `max_unavailable_percentage` | How many pods (as % of desired) may be **down** during the rollout |

Docs tip: for **GPU** workloads where you cannot afford extra nodes, people often set **max surge = 0%** and allow some **max unavailable** (catalogue model defaults commonly use **0% surge / 25% unavailable** — confirm on the app).

Implications:

- **Surge 0%** → the platform will **not** bring up an extra new pod before stopping an old one when that would exceed desired count. With **1 replica**, the only pod can be terminated **before** the replacement is Ready → **downtime** (and a long model reload).
- **Unavailable 25%** with few replicas rounds in ways that still allow the sole replica to go down.
- **Surge > 0%** needs spare GPU/CPU capacity or the new pod stays Pending (`pending-scheduling.md`) while old pods may already be draining.

Recommended reading for users: https://www.truefoundry.com/docs/rollout-strategy

## FAQ: we only changed replicas and the old pod went down

**Symptom (production):** Autoscale / replica bounds changed (e.g. min/max from 1–2 to 2–3). A **new ReplicaSet** appeared; the **existing pod went down**; traffic blipped or inference stopped until the new pod loaded.

**This is usually expected given the rollout strategy — not necessarily a platform bug.** Explain:

1. Fetch the app’s `rollout_strategy` from the live manifest / `get_applied_k8s_manifest`.
2. If `type: rolling_update` (or equivalent) with **`max_surge_percentage: 0`** and non-zero **`max_unavailable_percentage`**, say clearly that TrueFoundry will replace pods under those limits when a new revision is applied — including replica-only edits.
3. For **single-replica GPU model servers**, 0% surge means the old pod can stop before the new one is Ready → downtime equal to schedule + image pull + **model download/load** (minutes to hours without cache).
4. Mitigations to propose (edit live manifest, validate, apply with approval):
   - Raise **`max_surge_percentage`** (e.g. 25–100%) **if** spare GPUs exist so a new pod can become Ready before the old one stops.
   - Keep **minReplicas ≥ 2** in prod before risky applies, so unavailable % does not remove all capacity.
   - Use **canary** when they need traffic-controlled promotion (`search_docs` + schema).
   - Ensure **model cache PVC** works so replacement pods do not re-download weights (`model-serving-faq.md`, volumes playbook).
5. Verify with `list_k8s_pods`, Rollout/ReplicaSet objects, and events — not from `DEPLOY_SUCCESS` alone.

Do **not** tell the user “replica changes never recreate pods.” Do **not** skip reading their actual `rollout_strategy`.

## Canary and blue-green

- **Canary** — shift a traffic percentage to the new revision in steps; pause/promote. Use when they need controlled production exposure.
- **Blue-green** — bring up the full new set, cut traffic over, then tear down old.

Exact step fields vary — `get_manifest_json_schema` + docs. During canary, watch new pods + smoke tests; stuck analysis → `failure-modes/rollout-argocd.md`.

## Diagnose a bad rollout

| Observation | Next |
|---|---|
| New RS, old pod terminating, surge 0% | Expected under strategy — explain + mitigate |
| New pod Pending (GPU) while old already gone | Capacity + Karpenter (`pending-scheduling.md`) compounded by surge 0% |
| Rollout stuck / OutOfSync | `rollout-argocd.md` |
| Canary not advancing | Rollout CR / analysis metrics |

## Checklist

- [ ] Did I read the app’s actual `rollout_strategy` before calling behavior a bug?
- [ ] For replica-only prod changes on GPU models, did I warn about surge 0% / single-replica downtime?
- [ ] Did I propose concrete surge / min-replica / canary / cache mitigations?
- [ ] Did I validate + apply strategy edits only with approval?

For more info: `search_docs` with "rollout strategy", "canary", "rolling update", "autoscaling".
