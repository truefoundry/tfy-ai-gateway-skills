---
name: support-tickets
description: Create support tickets via Pylon when the user asks or when the agent cannot resolve a TrueFoundry-related issue.
---

**Support tickets** escalate TrueFoundry issues to the support team when the agent cannot resolve them.

## When to Offer

Offer a ticket when the question is about TrueFoundry but cannot be resolved — docs missing, tools failing, or outside technical scope (billing, contracts, enterprise setup). Ignore questions unrelated to TrueFoundry entirely.

## Write Flow

1. Call `get_me` — get user email and name.
2. Call `get_pylon_account_id` — get the tenant's Pylon account ID.
3. Construct title and description from conversation context — what the user asked, what was tried, why it failed. Create the ticket directly without asking the user to confirm.
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

5. Show **only** ticket number and title to the user. Do not show link or status.

### Fields

| Field | Required | Source |
|---|---|---|
| `account_id` | yes | `get_pylon_account_id` |
| `requester_email` | yes | `get_me` |
| `title` | yes | conversation context |
| `body_html` | yes | conversation context, HTML formatted |
| `priority` | no | `urgent`, `high`, `medium`, `low` — only if user mentioned urgency |
| `tags` | no | string array |

### Checklist

- [ ] Called `get_me` and `get_pylon_account_id`?
- [ ] Built title and description from conversation, not re-asked the user?
- [ ] Formatted description as HTML for `body_html`?
