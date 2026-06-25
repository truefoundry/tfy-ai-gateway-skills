---
name: support-tickets
description: Escalate unresolved TrueFoundry issues to the support team via Pylon. Use when the agent cannot answer a TrueFoundry question, tools return unexpected errors, or the user asks to create a support ticket.
---

## Trigger → Decide path

| User says | Path |
|---|---|
| "Create a ticket" / "raise a ticket" | → **Direct create** |
| "Connect me to TrueFoundry" / "talk to someone" | → **Explain and confirm**: explain the escalation is via a support ticket, proceed only if user confirms. |
| *(agent cannot answer or operation fails)* | → **Offer first**: present ticket offer as a separate paragraph. Proceed only if user accepts. |

Do not suggest other contact channels (website, Discord, email). The ticket is the only escalation path.

## Create flow

1. Call `get_me` — get user email and name.
2. Call `get_pylon_account_id` — get the tenant's Pylon account ID.
3. Construct title and description from conversation context. Do not ask the user to re-explain.
4. Select a priority based on context. Confirm with user via `ask_user_question` (Yes / No). If rejected, let user pick via `ask_user_question` with `urgent`, `high`, `medium`, `low`.
5. Call `create_issue`:

```json
{
  "account_id": "from-get-pylon-account-id",
  "title": "Unable to add image models for Bedrock",
  "body_html": "<p>User wanted to add image-mode Bedrock models.</p><ul><li>Called <code>list_providers</code>, filtered for image models</li><li><code>apply_manifest</code> returned: model type image not supported</li></ul><p>Likely needs platform-side fix.</p>",
  "requester_email": "from-get-me",
  "priority": "high"
}
```

6. Show ticket number, title, and that someone from TrueFoundry will follow up. Never show ticket link, URL, or status.

### Fields

| Field | Required | Source |
|---|---|---|
| `account_id` | yes | `get_pylon_account_id` |
| `requester_email` | yes | `get_me` |
| `title` | yes | conversation context |
| `body_html` | yes | conversation context, HTML formatted |
| `priority` | yes | `ask_user_question` confirmation |
| `tags` | no | string array |
