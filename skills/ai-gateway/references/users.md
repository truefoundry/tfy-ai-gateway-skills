---
name: users
description: Read for adding or inviting users, a user's status (active, invite pending, deactivated), resending an invite, resetting a password, deactivating, reactivating or deleting a user, and why a user can't be added. For giving a user roles or access, read `access-management.md`.
---

Users are people who log in to the tenant. Access is not part of the user: a new user gets only the baseline, and roles and grants are given separately (`access-management.md`).

## Find a user and their status

`list_users` with `query=<part of the email>` (matches email only) → `id`, `email`, `active`, `roles`, `metadata`. Deactivated users are hidden unless `showInvalidUsers: true`. Status, checked in this order:

| Status | When |
|---|---|
| Deactivated | `active: false` |
| Invite pending | `metadata.inviteAccepted: false` — invited, has not set a password yet |
| Registration pending | `metadata.registeredInIdp: false` — added without an invite, has not logged in yet |
| Active | otherwise |

`roles` lists the user's tenant roles. For everything they can access, use `list_grants` with `subjectType: user` and the `id`.

## Add or invite a user

`register_user` with `email`:
- `sendInviteEmail: true` emails a link to set a password, with `acceptInviteClientURL: "{controlPlaneUrl}/invite-accept"` (the page the link opens; required). Use it only when TrueFoundry manages login; with the tenant's own OAuth it returns 403.
- `sendInviteEmail: false` (default) adds the user without an email. Use it for users who sign in through SSO; they become active at their first login.

Every new user gets the **Member** role and joins the `everyone` team. No role or team can be set while adding: grant them afterwards (`access-management.md` → Tenant roles, `teams.md`). To add several users, call it once per email.

It needs the Manage Users permission. It fails when:
- **409** — the email is already in the tenant, whatever its status. Find it with `list_users` (with `showInvalidUsers: true`) and act on its status instead: resend the invite, or reactivate it.
- **403 "Manual provisioning is disabled"** — users can only arrive through SSO (just-in-time) or SCIM. An admin can enable Manual under Settings > Security & Access > Provisioning ([provisioning](https://www.truefoundry.com/docs/platform/user-management#user-provisioning)).
- **402 `PLAN_LIMIT_EXCEEDED`** — the plan's user limit is reached. Deactivated users still count; deleting one frees a seat.

## Resend an invite

`resend_user_invite` with `email` and `acceptInviteClientUrl: "{controlPlaneUrl}/invite-accept"`. Use it for an invite-pending user (`inviteAccepted: false`), or an email that is not in the tenant yet (that adds the user and sends the invite). Not for an active user: it marks the invite unaccepted. Needs Manage Users, and only when TrueFoundry manages login (403 otherwise). Manual provisioning must be on — same 403 and 402 as `register_user`.

## Reset a password

`reset_user_password` with `email` and `resetPasswordClientUrl: "{controlPlaneUrl}/reset-password"`. Emails a reset link to a user already in the tenant; it does not set the password. 404 if the email is not in the tenant. An invite-pending user has no password yet — resend the invite instead. Needs tenant-admin, and password login must be enabled.

## Deactivate or reactivate

- `deactivate_user` with `email`: the user can no longer log in, and their personal access tokens stop working. Roles, grants and team memberships are kept. Needs tenant-admin.
- `activate_user` with `email`: restores the user with everything they had. Needs the Manage Users permission.

Prefer deactivating over deleting when someone leaves: it is reversible.

## Delete

`delete_user` with the user's `id` (not the email). Permanent; needs tenant-admin. It fails (400) while the user holds any grant on a resource or belongs to a team other than `everyone`, so the admin can review that access first; `forceDelete: true` deletes the user with their access anyway — confirm with the user before using it. Their personal access tokens stay listed but stop working; revoke them from the user's row menu → **Revoke All PATs**.

## SSO and SCIM users

- With just-in-time provisioning on, a user is created at their first SSO login with the Member role. SSO groups do not assign roles; grant them in TrueFoundry. With SCIM, IdP groups become teams (`teams.md`).
- Users managed by SCIM have `isEditable: false`: they cannot be deactivated, reactivated or deleted here (400). Change them in the IdP.

Docs: [manage users](https://www.truefoundry.com/docs/platform/user-management).
