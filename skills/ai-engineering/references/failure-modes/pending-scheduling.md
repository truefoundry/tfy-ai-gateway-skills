---
name: pending-scheduling
description: Pod stuck Pending, FailedScheduling, GPU not allocated, Karpenter not provisioning, untolerated taints, node affinity mismatch. Read when get_application_state shows a Pending pod or events mention FailedScheduling / unschedulable — for GPU/capacity cases you must check autoscaler logs or ask the user for NodeClaim status, not stop at the pod event.
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

After `troubleshooting.md` Phase 1–2 have given you the application `id`, `clusterId` and a Pending pod:

0. **FailedMount first.** `Pending` is also what you see for volume mount failures, and those are **not** `FailedScheduling`. Call `list_application_events` for the app. If you see `FailedMount`, `FailedAttachVolume`, or PVC bind errors → stop and open `failure-modes/volumes-storage.md`.
1. Read the scheduler's reason: the pod's `message` and its `PodScheduled` condition in `get_application_state`, and `FailedScheduling` events from `list_application_events`.
2. `get_applied_k8s_manifest` — the pod's requests, nodeSelector/affinity, tolerations and topology constraints as applied.
3. **If the message is capacity / GPU / unschedulable — check provisioning next (do not stop at the pod event).** See **Karpenter / node provisioning** below. This is required for GPU scheduling problems, not optional.
4. `list_cluster_addons` + `get_cluster_status` when provisioning looks broken or addons look unhealthy.

Node lists, taints and allocatable capacity are not visible to any tool (`tools.md` → What no tool can see). The FailedScheduling message already summarises them ("0/5 nodes are available: 3 Insufficient nvidia.com/gpu, 2 node(s) had untolerated taint …"); work from it, and when you need the raw nodes, give the user `kubectl get nodes -L node.kubernetes.io/instance-type` / `kubectl describe node <name>`.

## Read the FailedScheduling message

The event message is usually enough to pick a branch. Common patterns:

| Message fragment | Meaning | Next |
|---|---|---|
| `insufficient cpu` / `insufficient memory` | Requests exceed free capacity on matching nodes | Compare applied requests with the instance sizes the user expects; then **Karpenter / autoscaler** if no node can grow |
| `insufficient nvidia.com/gpu` / `aws.amazon.com/neuron` | Accelerator resource missing or already allocated | GPU section **then Karpenter / autoscaler** — do not conclude without provisioning evidence |
| `had untolerated taint` | Pod lacks a matching toleration (control-plane, GPU, Neuron, custom) | The message names the taint; compare with tolerations in `get_applied_k8s_manifest` |
| `didn't match Pod's node affinity/selector` | nodeSelector / affinity too narrow | Inspect affinity in the applied manifest; often a wrong instance family or zone; if nodes never appear, still check Karpenter |
| `incompatible with provisioner` / `NodePool` / `no instance type satisfied` | Karpenter cannot find an instance type for the combined requirements | **Karpenter section required** — usually a **requirements conflict**, not "cluster is full" |
| `0/N nodes are available` with several reasons combined | Multiple filters — list every reason; the real blocker is often the last/narrowest one | Do not stop at the first clause; if no node is coming up, read Karpenter / autoscaler |

## GPU and accelerator cases

Symptoms from the field: nodes come up but pods stay Pending; device plugin not advertising GPUs; Inferentia vs NVIDIA mix-ups; multi-GPU notebooks that no instance type can satisfy; **GPU request Pending forever while Karpenter never launches a node**.

Check in order:

1. **Pod requests** — `get_applied_k8s_manifest`. Confirm `nvidia.com/gpu` (or Neuron) count and whether CPU/memory + GPU + zone + capacity-type constraints can coexist on one instance.
2. **Device plugin** — if a GPU node exists (other pods on it in `get_application_state`, or the user confirms) but the message still says `insufficient nvidia.com/gpu`, the GPU operator / device plugin is likely broken: check `list_cluster_addons` for GPU operator health, and give the user `kubectl describe node <name>` to confirm `allocatable` shows `nvidia.com/gpu: 0`. This is **not** fixed by changing the application CPU request.
3. **Taints** — GPU nodes often carry taints. The workload must tolerate them (TrueFoundry GPU node pools usually inject this; custom node pools may not).
4. **Wrong accelerator family** — Neuron taints (`aws.amazon.com/neuron`) will reject NVIDIA GPU pods and vice versa. The FailedScheduling text names the taint.
5. **Multi-GPU + instance filters** — combining `nvidia.com/gpu: 2` with a narrow instance family/size allow-list often yields `no instance type satisfied`. Quote that phrase to the user; the fix is relaxing instance requirements or reducing GPU count, not "waiting longer".
6. **Always run Karpenter / autoscaler** when no suitable GPU node appears. GPU Pending with no node coming up is a provisioning problem until proven otherwise.

## Karpenter / node provisioning

**When to run this section (required, not optional):** FailedScheduling mentions provisioners/NodePools/`no instance type`; GPU/accelerator insufficient; insufficient cpu/memory with no spare nodes; nodes never appear after several minutes; user says Karpenter / node pool / autoscaling.

Do these in order:

1. **`get_cluster_autoscaler_logs`** with the cluster `id`.
   - **Azure / GCP:** this is the provisioning log stream (cluster-autoscaler or NAP). Read the recent lines for scale-up refused, quota, or instance-type unavailable — quote them.
   - **AWS:** this tool returns **501 / not implemented**. That is expected. Continue with step 2.
2. **Events** — `list_application_events` often carries Karpenter's own events on the pod (`Nominated`, `FailedScheduling` from karpenter, launch errors). Quote them.
3. **NodeClaims / NodePools (AWS Karpenter)** — no tool can read them. Ask the user to run `kubectl get nodeclaims` and `kubectl describe nodeclaim <name>` (launch failures: IAM, quotas, subnet, AMI, spot capacity, instance type unavailable), and `kubectl get nodepool <name> -o yaml` to compare requirements (family In/NotIn, zone, capacity-type, arch, GPU instance families) with the pod.
4. **`list_cluster_addons`** — Karpenter / karpenter-config / GPU operator not installed or unhealthy means no provisioning path. Say which addon.

**Before** concluding the pod is incompatible with a NodePool, you must have the pod scheduling fields (applied manifest) **and** provisioning evidence (autoscaler logs, Karpenter events, or NodeClaim output from the user). Guessing from the pod event alone causes wrong "relax the GPU count" advice when the real issue is quota, zone, capacity-type, or AMI. If you do not have that evidence yet, say so and give the commands.

Karpenter **controller** logs live in a system namespace no tool can read. Ask the user, or follow `references/support-tickets.md` with the evidence you already have — do not pretend you fetched `kube-system`.

## What not to do

- Do not call `get_logs` on a Pending pod and report "no logs, so it's fine". There are no application logs until the container starts.
- Do not skip Karpenter / autoscaler when GPU or capacity scheduling is the failure — pod events alone are incomplete.
- Do not treat exit code theories — the container never ran.
- Do not recommend increasing replicas; that creates more Pending pods.
- Do not claim OOM or CrashLoop from Pending.

## Checklist

- [ ] Did I read the FailedScheduling message (pod `message` / events) before guessing?
- [ ] Did I read requests/affinity/tolerations from `get_applied_k8s_manifest`?
- [ ] For GPU / capacity Pending, did I call `get_cluster_autoscaler_logs` (and handle AWS 501), read Karpenter events, and ask for NodeClaim / NodePool output where needed?
- [ ] For GPU, did I check the GPU operator in `list_cluster_addons`?
- [ ] Did I name what I could not see and give the user the `kubectl` command for it?
- [ ] Did I avoid application-log conclusions for a pod that never scheduled?

For more info: `search_docs` with "GPU", "node pool", "karpenter", "pending pod".
