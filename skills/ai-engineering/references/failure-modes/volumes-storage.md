---
name: volumes-storage
description: FailedMount, PVC Pending, EFS/NFS access denied, volume not attaching, storage capacity. Read when events mention FailedMount, MountVolume, PVC, CSI, EFS, NFS, or the user says the pod cannot see their volume.
---

Volume failures often look like Pending or CrashLoop depending on timing: the pod may stay Pending on `FailedMount`, or start and crash when the app cannot write to the mount path.

## Triage

1. `list_application_events` — scan for `FailedMount`, `FailedAttachVolume`, `ProvisioningFailed`; the message usually names the PVC, volume and error.
2. `get_applied_k8s_manifest` — the pod's volumes and mount paths as applied.
3. PVC objects are not visible to any tool. When the event is not enough, ask the user for `kubectl get pvc -n <workspace>` and `kubectl describe pvc <name> -n <workspace>`.
4. Confirm the TrueFoundry Volume application (if used) via `list_applications` / `get_application` — volumes are separate applications that services mount.

Steps 1, 2 and 4 are independent: issue them in one message. Live mount events last about an hour; older windows show only lifecycle events, so ask for `kubectl describe pvc` sooner for old failures.

## Message → cause

| Pattern | Cause | Direction |
|---|---|---|
| `timeout waiting for volume` / attach errors | Cloud disk attach limits, wrong AZ | Node AZ vs volume AZ; cloud attach quota |
| `access denied` / NFS mount.nfs4 errors / EFS watchdog | Filesystem policy, security group, wrong access point | EFS/NFS network + IAM/access point config — usually infra |
| PVC `Pending` with ProvisioningFailed | StorageClass / CSI driver / quota | `list_cluster_addons` for CSI; storage class name |
| Multi-attach error for ReadWriteOnce | Two pods mounting one RWO volume | Scale to 1, or use RWX-capable storage |
| Mount path empty after "success" | Wrong mountPath vs what the app writes | Compare the service volume `mount_path` to where the app writes (e.g. the app writes to `/app/data`) |

## TrueFoundry volumes

- A Volume application must exist and be healthy before a Service can mount it.
- Recreating or deleting the volume loses its data. Changing `mount_path` keeps the data but mounts it elsewhere, so the app sees an empty directory at its old path — call this out if the user "fixed" storage that way.
- Size increases and storage class changes have cloud-specific limits; do not invent resize steps — `search_docs` for volumes.

## What not to do

- Do not treat FailedMount as CrashLoop application bugs.
- Do not recommend increasing CPU/memory for mount errors.
- Platform system CSI namespaces may be unreadable — say so if you cannot inspect the CSI driver pods.

## Checklist

- [ ] Did I read FailedMount / PVC events before looking at app logs?
- [ ] When the events were not enough, did I ask the user for the PVC status (`kubectl describe pvc`)?
- [ ] Did I confirm `mount_path` matches what the application expects?
- [ ] For RWO volumes, did I check replica count / multi-attach?

For more info: `search_docs` with "volume", "persistent volume", "storage".
