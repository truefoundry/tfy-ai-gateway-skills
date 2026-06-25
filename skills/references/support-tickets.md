---
name: support-tickets
description: Escalate unresolved TrueFoundry issues to the support team via Pylon. Use when the agent cannot answer a TrueFoundry question, tools return unexpected errors, or the user asks to create a support ticket.
---

## Trigger

Offer a ticket when the question is about TrueFoundry but cannot be resolved — docs missing, tools failing, or outside technical scope (billing, contracts, enterprise setup).

**User explicitly asks to create a ticket** → create it directly, no confirmation needed, check for priority and some details from user
**Agent cannot answer or an operation fails** → offer to create a ticket first, if user wants to create ticket, then create the ticket 

## Presentation rules

- Present the ticket offer as a **separate paragraph**, not inline with the answer.
- Do not suggest other contact channels (website, Discord, email). The ticket is the only escalation path.
- After creation, show only ticket number and title. No link, no status.

## Write flow

1. Call `get_me` — get user email and name.
2. Call `get_pylon_account_id` — get the tenant's Pylon account ID.
3. Construct title and description from conversation context. Do not ask the user to re-explain.
4. Call `create_issue`:

```json
{
  "account_id": "from-get-pylon-account-id",
  "title": "Unable to add image models for Bedrock",
  "body_html": "<p>User wanted to add image-mode Bedrock models.</p><ul><li>Called <code>list_providers</code>, filtered for image models</li><li><code>apply_manifest</code> returned: model type image not supported</li></ul><p>Likely needs platform-side fix.</p>",
  "requester_email": "from-get-me",
  "priority": "high"
}
```

### Fields

| Field | Required | Source |
|---|---|---|
| `account_id` | yes | `get_pylon_account_id` |
| `requester_email` | yes | `get_me` |
| `title` | yes | conversation context |
| `body_html` | yes | conversation context, HTML formatted |
| `priority` | no | `urgent`, `high`, `medium`, `low` — only if user mentioned urgency |
| `tags` | no | string array |
