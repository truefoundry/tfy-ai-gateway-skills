---
name: volumes-storage
description: FailedMount, PVC Pending, EFS/NFS access denied, volume not attaching, storage capacity. Read when events mention FailedMount, MountVolume, PVC, CSI, EFS, NFS, or the user says the pod cannot see their volume.
---

Volume failures often look like Pending or CrashLoop depending on timing: the pod may stay Pending on `FailedMount`, or start and crash when the app cannot write to the mount path.

## Triage

1. `list_k8s_events` / `list_application_events` — filter or scan for `FailedMount`, `FailedAttachVolume`, `ProvisioningFailed`.
2. `list_k8s_objects` for PVCs in the workspace namespace: `apiVersion=v1`, `resource=persistentvolumeclaims`.
3. `describe_k8s_object` on the stuck PVC and on the Pod (volume mounts section).
4. Confirm the TrueFoundry Volume application (if used) via `list_applications` / `get_application` — volumes are separate applications that services mount.

## Message → cause

| Pattern | Cause | Direction |
|---|---|---|
| `timeout waiting for volume` / attach errors | Cloud disk attach limits, wrong AZ | Node AZ vs volume AZ; cloud attach quota |
| `access denied` / NFS mount.nfs4 errors / EFS watchdog | Filesystem policy, security group, wrong access point | EFS/NFS network + IAM/access point config — usually infra |
| PVC `Pending` with ProvisioningFailed | StorageClass / CSI driver / quota | `list_cluster_addons` for CSI; storage class name |
| Multi-attach error for ReadWriteOnce | Two pods mounting one RWO volume | Scale to 1, or use RWX-capable storage |
| Mount path empty after "success" | Wrong mountPath vs what the app writes | Compare service volume mountPath to app config (e.g. must be `/app/data`) |

## TrueFoundry volumes

- A Volume application must exist and be healthy before a Service can mount it.
- Changing mount path or recreating the volume **wipes** data the app expected — call this out if the user "fixed" storage by creating a new volume.
- Size increases and storage class changes have cloud-specific limits; do not invent resize steps — `search_docs` for volumes.

## What not to do

- Do not treat FailedMount as CrashLoop application bugs.
- Do not recommend increasing CPU/memory for mount errors.
- Platform system CSI namespaces may be unreadable — say so if you cannot inspect the CSI driver pods.

## Checklist

- [ ] Did I read FailedMount / PVC events before looking at app logs?
- [ ] Did I inspect the PVC object status?
- [ ] Did I confirm mountPath matches what the application expects?
- [ ] For RWO volumes, did I check replica count / multi-attach?

For more info: `search_docs` with "volume", "persistent volume", "storage".
