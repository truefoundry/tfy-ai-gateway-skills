---
name: support-tickets
description: Create support tickets via Pylon when the user asks or when the agent cannot resolve their issue.
---

**Support tickets** let users escalate issues to the TrueFoundry support team directly through the agent.

## When to Offer

If you cannot resolve the user's issue — docs don't have the answer, tools return unexpected errors, or the question is outside your scope — tell the user you can create a support ticket for them. Example:

> "I wasn't able to resolve this. Would you like me to create a support ticket so the TrueFoundry team can help?"

## Creating a Support Ticket

### Phase 1: Get User Identity and Account

1. Call `get_me` — get the user's email and name.
2. Call `get_pylon_account_id` — get the `pylonAccountId` for the tenant. Never ask the user for this.

### Phase 2: Construct Ticket from Conversation Context

The user has already described the problem. Do NOT ask them to re-explain. Build the ticket from the conversation:
- **Title** — concise summary derived from the user's question/issue
- **Description** — what the user asked, what you tried, why it couldn't be resolved
- **Priority** — only include if the user explicitly mentioned urgency
- Confirm the drafted title and description with the user before creating

### Phase 3: Create the Ticket

Call `create_issue` with JSON:

```json
{
  "account_id": "91ba5de7-...",
  "title": "Unable to add image models for Bedrock",
  "body_html": "<p>User wanted to add image-mode models from AWS Bedrock provider account.</p><p>What was tried:</p><ul><li>Called <code>list_providers</code> and filtered for Bedrock image models</li><li>Built manifest with matching model IDs</li><li><code>apply_manifest</code> returned error: model type <code>image</code> not supported for this provider</li></ul><p>This may require a platform-side fix or updated provider support.</p>",
  "requester_email": "user@company.com",
  "priority": "high"
}
```

Fields:
- `account_id` (required) — from `get_pylon_account_id`
- `requester_email` (required) — from `get_me`
- `title` (required) — from Phase 2
- `body_html` (required) — HTML formatted description. Use `<p>` for paragraphs, `<ul>/<li>` for lists, `<code>` for code/errors
- `priority` (optional) — `urgent`, `high`, `medium`, `low`
- `tags` (optional) — string array

After creation, show **only** the ticket number and title. Do NOT show the ticket link or status.

### Checklist

- [ ] Did I call `get_me` for the user's email?
- [ ] Did I call `get_pylon_account_id` (not ask the user for it)?
- [ ] Did I build the title and description from the conversation (not ask the user to re-explain)?
- [ ] Did I confirm the draft with the user before creating?
- [ ] Did I format the description as HTML for `body_html`?
- [ ] If I got a 429 error, did I wait and retry (Pylon rate limit: 10 req/min)?
