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

1. Take `email` from the session context. If it is absent (non-user session), ask the user for a contact email.
2. Call `get_pylon_account_id`; use `pylonAccountId` from the response as `account_id`.
3. Write the title and body from the conversation; do not ask the user to re-explain. If key details (error text, entity names) are no longer in the conversation, ask the user for just those.
4. Pick a priority using the severity guide below and confirm it with the user via `ask_user_question` (Yes / No); if rejected, let them pick from the options. If you are a sub-agent and `ask_user_question` is not available, stop and return the question to the main agent.

**Severity guide:**

| Priority | When to use |
|---|---|
| `urgent` | Production system is completely down. Never for feature requests or questions. |
| `high` | Service degraded, or feature request blocking an imminent deadline |
| `medium` | Blocking work but has a workaround, or feature request with a timeline |
| `low` | Question, nice-to-have feature request, or non-blocking issue |

**If the user picks `urgent`:** ask clarifying questions about the impact (which service, how many users, when did it start). Only proceed with `urgent` if a production system is fully down. Otherwise, suggest the appropriate priority from the table above.

5. Call `create_issue`. The requester is emailed the ticket and can reply to it, so write `body_html` as a message from the user to the support team, not a third-person summary:

```json
{
  "account_id": "<pylonAccountId from get_pylon_account_id>",
  "title": "Unable to add image models for Bedrock",
  "body_html": "<p>Hi TrueFoundry team,</p><p>I'm trying to add image-mode Bedrock models. <code>apply_manifest</code> returned: model type image not supported. Can you enable this or suggest a workaround?</p>",
  "requester_email": "<email from the session context>",
  "priority": "high"
}
```

6. Show the ticket number and title, and say the user will get the ticket by email and can reply there. Do not show the link or status.

### Fields

| Field | Required | Source |
|---|---|---|
| `account_id` | yes | `pylonAccountId` from `get_pylon_account_id` |
| `requester_email` | yes | session context `email`, or asked from the user |
| `title` | yes | conversation context |
| `body_html` | yes | conversation context, HTML, addressed to the support team |
| `priority` | no (always set it after the user confirms) | `urgent`, `high`, `medium` or `low` |
| `tags` | no | string array |
