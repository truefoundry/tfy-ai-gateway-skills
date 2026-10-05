---
name: pending-scheduling
description: Pod stuck Pending, FailedScheduling, GPU not allocated, Karpenter not provisioning, untolerated taints, node affinity mismatch. Read when list_k8s_pods shows Pending or events mention FailedScheduling / unschedulable — for GPU/capacity cases you must check Karpenter / autoscaler logs, not stop at the pod event.
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

0. **FailedMount first.** `Pending` is also what you see for volume mount failures, and those are **not** `FailedScheduling`. Call `list_k8s_events` (no FailedScheduling-only filter yet) / `list_application_events`. If you see `FailedMount`, `FailedAttachVolume`, or PVC bind errors → stop and open `failure-modes/volumes-storage.md`.
1. `list_k8s_events` with `fieldSelector=reason=FailedScheduling` (and/or `list_application_events` for the same window).
2. `describe_k8s_object` on the **Pod** — you need requests, nodeSelector/affinity, tolerations, and topology constraints. The list projection does not include these.
3. `list_k8s_nodes` — capacity, taints, readiness. For GPUs, try `labelSelector=nvidia.com/gpu.present=true` (or the cloud's equivalent).
4. **If the message is capacity / GPU / unschedulable and no fitting Ready node exists — check Karpenter / autoscaler next (do not stop at the pod event).** See **Karpenter / node provisioning** below. This is required for GPU scheduling problems, not optional.
5. `list_cluster_addons` + `get_cluster_status` when provisioning tools fail or addons look unhealthy.

## Read the FailedScheduling message

The event message is usually enough to pick a branch. Common patterns:

| Message fragment | Meaning | Next |
|---|---|---|
| `insufficient cpu` / `insufficient memory` | Requests exceed free capacity on matching nodes | Compare pod requests vs node allocatable; then **Karpenter / autoscaler** if no node can grow |
| `insufficient nvidia.com/gpu` / `aws.amazon.com/neuron` | Accelerator resource missing or already allocated | GPU section **then Karpenter / autoscaler** — do not conclude without provisioning logs/NodeClaims |
| `had untolerated taint` | Pod lacks a matching toleration (control-plane, GPU, Neuron, custom) | Compare taints on nodes vs pod tolerations from `describe_k8s_object` |
| `didn't match Pod's node affinity/selector` | nodeSelector / affinity too narrow | Inspect affinity; often a wrong instance family or zone; if nodes never appear, still check Karpenter |
| `incompatible with provisioner` / `NodePool` / `no instance type satisfied` | Karpenter cannot find an instance type for the combined requirements | **Karpenter section required** — usually a **requirements conflict**, not "cluster is full" |
| `0/N nodes are available` with several reasons combined | Multiple filters — list every reason; the real blocker is often the last/narrowest one | Do not stop at the first clause; if no node is coming up, read Karpenter / autoscaler |

## GPU and accelerator cases

Symptoms from the field: nodes come up but pods stay Pending; device plugin not advertising GPUs; Inferentia vs NVIDIA mix-ups; multi-GPU notebooks that no instance type can satisfy; **GPU request Pending forever while Karpenter never launches a node**.

Check in order:

1. **Pod requests** — `describe_k8s_object` Pod. Confirm `nvidia.com/gpu` (or Neuron) count and whether CPU/memory + GPU + zone + capacity-type constraints can coexist on one instance.
2. **Nodes** — `list_k8s_nodes` with a GPU label. If nodes exist but `allocatable` has `nvidia.com/gpu: 0`, the GPU operator / device plugin is broken — `list_cluster_addons` for the GPU operator health. This is **not** fixed by changing the application CPU request.
3. **Taints** — GPU nodes often carry taints. The workload must tolerate them (TrueFoundry GPU node pools usually inject this; custom node pools may not).
4. **Wrong accelerator family** — Neuron taints (`aws.amazon.com/neuron`) will reject NVIDIA GPU pods and vice versa. The FailedScheduling text names the taint.
5. **Multi-GPU + instance filters** — combining `nvidia.com/gpu: 2` with a narrow instance family/size allow-list often yields `no instance type satisfied`. Quote that phrase to the user; the fix is relaxing instance requirements or reducing GPU count, not "waiting longer".
6. **Always open Karpenter / autoscaler** when no suitable GPU node is Ready (or NodeClaims never appear). GPU Pending with empty node list is a provisioning problem until proven otherwise.

## Karpenter / node provisioning

**When to run this section (required, not optional):** FailedScheduling mentions provisioners/NodePools/`no instance type`; GPU/accelerator insufficient; insufficient cpu/memory with no spare nodes; nodes never appear after several minutes; user says Karpenter / node pool / autoscaling.

Do these in order:

1. **`get_cluster_autoscaler_logs`** with the cluster `id`.
   - **Azure / GCP:** this is the provisioning log stream (cluster-autoscaler or NAP). Read the recent lines for scale-up refused, quota, or instance-type unavailable — quote them.
   - **AWS:** this tool returns **501 / not implemented**. That is expected. Do **not** stop or invent kubectl into `kube-system`. Continue with NodeClaims (step 2) — those are the AWS Karpenter signal.
2. **`list_k8s_objects`** `apiVersion=karpenter.sh/v1` `resource=nodeclaims` (try `v1beta1` if v1 404s). Match claims to the NodePool named in the event. Read **status conditions** and events on the claim (launch failures: IAM, quotas, subnet, AMI, spot capacity, instance type unavailable). Treat NodeClaim status as the Karpenter "why didn't a node start" answer on AWS.
3. **`list_k8s_objects`** for `nodepools` (and on AWS, `ec2nodeclasses.karpenter.k8s.aws` when relevant) — confirm requirements are compatible with the pod (family In/NotIn, zone, capacity-type, arch, GPU instance families).
4. **`list_cluster_addons`** — Karpenter / karpenter-config / GPU operator not installed or unhealthy means no provisioning path. Say which addon.

**Before** concluding the pod is incompatible with a NodePool, you must have read **both** the pod scheduling fields and the NodePool requirements, **and** attempted autoscaler logs or NodeClaim status. Guessing from the pod event alone causes wrong "relax the GPU count" advice when the real issue is quota, zone, capacity-type, or AMI.

Karpenter **controller** pods live in a system namespace (often `kube-system` / `karpenter`) and are usually **not** readable via workspace-scoped `get_k8s_pod_logs`. Prefer `get_cluster_autoscaler_logs` (non-AWS) or NodeClaim status (AWS). If you still need controller logs, ask the user / follow `support-tickets.md` with the NodeClaim evidence you already have — do not pretend you fetched `kube-system`.

## What not to do

- Do not call `get_logs` / `get_k8s_pod_logs` on a Pending pod and report "no logs, so it's fine". There are no application logs until the container starts.
- Do not skip Karpenter / autoscaler when GPU or capacity scheduling is the failure — pod events alone are incomplete.
- Do not treat exit code theories — the container never ran.
- Do not recommend increasing replicas; that creates more Pending pods.
- Do not claim OOM or CrashLoop from Pending.

## Checklist

- [ ] Did I read FailedScheduling (or equivalent) events before guessing?
- [ ] Did I `describe_k8s_object` the Pod for requests/affinity/tolerations?
- [ ] Did I compare against real nodes (capacity + taints)?
- [ ] For GPU / capacity Pending, did I call `get_cluster_autoscaler_logs` (and handle AWS 501) **and** inspect NodeClaim/NodePool objects?
- [ ] For GPU, did I verify allocatable GPUs on nodes / addon health?
- [ ] Did I avoid application-log conclusions for a pod that never scheduled?

For more info: `search_docs` with "GPU", "node pool", "karpenter", "pending pod".
