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

After `troubleshooting.md` Phase 1–2 have given you the application `id`, `clusterId` and a Pending pod (if they are no longer in the conversation, resolve them again):

1. Issue in one message: `list_application_events` (with a `startTs` covering the Pending period), `get_applied_k8s_manifest` (requests, nodeSelector/affinity, tolerations, topology constraints as applied) and `list_clusters attributes=["id","name","manifest.cluster_type"]`. Reuse `get_application_state` if it is still in the conversation.
2. **FailedMount first.** `Pending` with a `node` set is not a scheduling problem: `FailedMount`, `FailedAttachVolume` or PVC bind errors in the events → stop and open `failure-modes/volumes-storage.md`.
3. Read the scheduler's reason: the `PodScheduled` condition with `reason: Unschedulable` in `get_application_state` (its `message` is "0/N nodes are available: …") and `FailedScheduling` events. Live events last about an hour; older windows show only a lifecycle "pending" event without the message.
4. **If the message is capacity / GPU / unschedulable — check provisioning next (do not stop at the pod event).** See **Karpenter / node provisioning** below. This is required for GPU scheduling problems, not optional.

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
2. **Device plugin** — if a GPU node exists (other pods on it in `get_application_state`, or the user confirms) but the message still says `insufficient nvidia.com/gpu`, the GPU operator / device plugin is likely broken: confirm the GPU operator is installed (`list_cluster_addons`), check its pods with `get_application_state` on its `applicationId`, and give the user `kubectl describe node <name>` to confirm `allocatable` shows `nvidia.com/gpu: 0`. This is **not** fixed by changing the application CPU request.
3. **Taints** — GPU nodes often carry taints. The workload must tolerate them (TrueFoundry GPU node pools usually inject this; custom node pools may not).
4. **Wrong accelerator family** — Neuron taints (`aws.amazon.com/neuron`) will reject NVIDIA GPU pods and vice versa. The FailedScheduling text names the taint.
5. **Multi-GPU + instance filters** — combining `nvidia.com/gpu: 2` with a narrow instance family/size allow-list often yields `no instance type satisfied`. Quote that phrase to the user; the fix is relaxing instance requirements or reducing GPU count, not "waiting longer".
6. **Always run Karpenter / autoscaler** when no suitable GPU node appears. GPU Pending with no node coming up is a provisioning problem until proven otherwise.

## Karpenter / node provisioning

**When to run this section (required, not optional):** FailedScheduling mentions provisioners/NodePools/`no instance type`; GPU/accelerator insufficient; insufficient cpu/memory with no spare nodes; nodes never appear after several minutes; user says Karpenter / node pool / autoscaling.

Pick the branch from `manifest.cluster_type` and issue its calls together with `list_cluster_addons` in one message:

- **`aws-eks` → Karpenter.** Skip `get_cluster_autoscaler_logs` (it returns 501). Karpenter's own pod events (`Nominated`, karpenter `FailedScheduling`, launch errors) are in `list_application_events` — quote them. NodeClaims / NodePools are not readable by any tool: ask the user for `kubectl get nodeclaims`, `kubectl describe nodeclaim <name>` (launch failures: IAM, quotas, subnet, AMI, spot capacity, instance type unavailable) and `kubectl get nodepool <name> -o yaml` to compare requirements (family In/NotIn, zone, capacity-type, arch, GPU instance families) with the pod.
- **`azure-aks` / `gcp-gke-standard` → `get_cluster_autoscaler_logs`** with the cluster `id` and `direction: "desc"` (the default is the oldest 100 lines of the last hour). Quote scale-up refused, quota, or instance-type-unavailable lines. Karpenter is not supported there; skip NodeClaims.
- **`generic` / `civo-talos`** — neither applies; check `list_cluster_addons` and ask the user how nodes are provisioned.

In every branch, `list_cluster_addons` tells you whether Karpenter / karpenter-config / the GPU operator is installed; a missing one means no provisioning path — say which. It has no health field: check an installed addon with `get_application_state` on its `applicationId`.

**Before** concluding the pod is incompatible with a NodePool, you must have the pod scheduling fields (applied manifest) **and** provisioning evidence (autoscaler logs, Karpenter events, or NodeClaim output from the user). Guessing from the pod event alone causes wrong "relax the GPU count" advice when the real issue is quota, zone, capacity-type, or AMI. If you do not have that evidence yet, say so and give the commands.

Karpenter **controller** logs live in `kube-system`, which no tool can read. Ask the user, or follow `references/support-tickets.md` with the evidence you gathered (re-read it if it is no longer in the conversation) — do not pretend you fetched `kube-system`.

## What not to do

- Do not call `get_logs` on a Pending pod and report "no logs, so it's fine". There are no application logs until the container starts.
- Do not skip Karpenter / autoscaler when GPU or capacity scheduling is the failure — pod events alone are incomplete.
- Do not treat exit code theories — the container never ran.
- Do not recommend increasing replicas; that creates more Pending pods.
- Do not claim OOM or CrashLoop from Pending.

## Checklist

- [ ] Did I read the scheduler's message (`Unschedulable` condition / events) before guessing?
- [ ] Did I read requests/affinity/tolerations from `get_applied_k8s_manifest`?
- [ ] For GPU / capacity Pending, did I follow the `cluster_type` branch (autoscaler logs on Azure/GCP; Karpenter events and NodeClaim / NodePool output from the user on AWS)?
- [ ] For GPU, did I check the GPU operator in `list_cluster_addons`?
- [ ] Did I name what I could not see and give the user the `kubectl` command for it?
- [ ] Did I avoid application-log conclusions for a pod that never scheduled?

For more info: `search_docs` with "GPU", "node pool", "karpenter", "pending pod".
