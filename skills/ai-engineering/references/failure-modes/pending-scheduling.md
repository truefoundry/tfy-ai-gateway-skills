---
name: pending-scheduling
description: Pod stuck Pending, FailedScheduling, GPU not allocated, Karpenter not provisioning, untolerated taints, node affinity mismatch. Read when list_k8s_pods shows Pending or events mention FailedScheduling / unschedulable.
---

A `Pending` pod is waiting for a node. Kubernetes will leave it there forever. The deployment may still show `DEPLOY_SUCCESS`. Treat Pending as a first-class failure mode, not a transient state, once it has lasted more than a couple of minutes.

## Contents
- Triage sequence
- Read the FailedScheduling message
- GPU and accelerator cases
- Karpenter / node provisioning
- What not to do
- Checklist

## Triage sequence

After `troubleshooting.md` Phase 1–2 have given you `clusterId`, `namespace`, and a Pending pod name:

1. `list_k8s_events` with `fieldSelector=reason=FailedScheduling` (and/or `list_application_events` for the same window).
2. `describe_k8s_object` on the **Pod** — you need requests, nodeSelector/affinity, tolerations, and topology constraints. The list projection does not include these.
3. `list_k8s_nodes` — capacity, taints, readiness. For GPUs, try `labelSelector=nvidia.com/gpu.present=true` (or the cloud's equivalent).
4. If no suitable node exists and the cluster uses Karpenter: `list_k8s_objects` for NodeClaims / NodePools (cluster-scoped).
5. If NodeClaims never appear or fail: `get_cluster_autoscaler_logs`, `list_cluster_addons`, `get_cluster_status`.

## Read the FailedScheduling message

The event message is usually enough to pick a branch. Common patterns:

| Message fragment | Meaning | Next |
|---|---|---|
| `insufficient cpu` / `insufficient memory` | Requests exceed free capacity on matching nodes | Compare pod requests vs node allocatable; consider lowering requests or adding nodes |
| `insufficient nvidia.com/gpu` / `aws.amazon.com/neuron` | Accelerator resource missing or already allocated | Check GPU nodes + device plugin; see GPU section |
| `had untolerated taint` | Pod lacks a matching toleration (control-plane, GPU, Neuron, custom) | Compare taints on nodes vs pod tolerations from `describe_k8s_object` |
| `didn't match Pod's node affinity/selector` | nodeSelector / affinity too narrow | Inspect affinity; often a wrong instance family or zone |
| `incompatible with provisioner` / `NodePool` / `no instance type satisfied` | Karpenter cannot find an instance type for the combined requirements | See Karpenter section — this is usually a **requirements conflict**, not "cluster is full" |
| `0/N nodes are available` with several reasons combined | Multiple filters — list every reason; the real blocker is often the last/narrowest one | Do not stop at the first clause |

## GPU and accelerator cases

Symptoms from the field: nodes come up but pods stay Pending; device plugin not advertising GPUs; Inferentia vs NVIDIA mix-ups; multi-GPU notebooks that no instance type can satisfy.

Check in order:

1. **Pod requests** — `describe_k8s_object` Pod. Confirm `nvidia.com/gpu` (or Neuron) count and whether CPU/memory + GPU + zone + capacity-type constraints can coexist on one instance.
2. **Nodes** — `list_k8s_nodes` with a GPU label. If nodes exist but `allocatable` has `nvidia.com/gpu: 0`, the GPU operator / device plugin is broken — `list_cluster_addons` for the GPU operator health. This is **not** fixed by changing the application CPU request.
3. **Taints** — GPU nodes often carry taints. The workload must tolerate them (TrueFoundry GPU node pools usually inject this; custom node pools may not).
4. **Wrong accelerator family** — Neuron taints (`aws.amazon.com/neuron`) will reject NVIDIA GPU pods and vice versa. The FailedScheduling text names the taint.
5. **Multi-GPU + instance filters** — combining `nvidia.com/gpu: 2` with a narrow instance family/size allow-list often yields `no instance type satisfied`. Quote that phrase to the user; the fix is relaxing instance requirements or reducing GPU count, not "waiting longer".

## Karpenter / node provisioning

When FailedScheduling mentions provisioners/NodePools, or nodes never appear:

1. `list_k8s_objects` `apiVersion=karpenter.sh/v1` `resource=nodeclaims` (try `v1beta1` if v1 404s). Look for claims matching the NodePool named in the event — status conditions explain launch failures (IAM, quotas, subnet, AMI).
2. `list_k8s_objects` for `nodepools` — confirm the pool's requirements are compatible with the pod (family In/NotIn, zone, capacity-type, arch).
3. `get_cluster_autoscaler_logs` — when NodeClaims are missing or cycling.
4. `list_cluster_addons` — Karpenter addon not installed/healthy means no provisioning path.

**Before** concluding the pod is incompatible with a NodePool, you must have read **both** the pod scheduling fields and the NodePool requirements. Guessing from the event alone causes wrong "relax the GPU count" advice when the real issue is a zone or capacity-type mismatch.

Karpenter controller pods live in a system namespace (often `kube-system`) and are usually not readable via workspace-scoped tools — use `get_cluster_autoscaler_logs` instead of inventing kubectl against `kube-system`.

## What not to do

- Do not call `get_logs` / `get_k8s_pod_logs` on a Pending pod and report "no logs, so it's fine". There are no logs until the container starts.
- Do not treat exit code theories — the container never ran.
- Do not recommend increasing replicas; that creates more Pending pods.
- Do not claim OOM or CrashLoop from Pending.

## Checklist

- [ ] Did I read FailedScheduling (or equivalent) events before guessing?
- [ ] Did I `describe_k8s_object` the Pod for requests/affinity/tolerations?
- [ ] Did I compare against real nodes (capacity + taints)?
- [ ] For GPU, did I verify allocatable GPUs on nodes / addon health?
- [ ] For Karpenter, did I inspect NodeClaim/NodePool objects rather than stopping at the event text?
- [ ] Did I avoid log-based conclusions for a pod that never scheduled?

For more info: `search_docs` with "GPU", "node pool", "karpenter", "pending pod".
