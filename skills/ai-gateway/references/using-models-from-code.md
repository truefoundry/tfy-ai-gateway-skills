---
name: using-models-from-code
description: Call AI Gateway models from code or a third-party tool — OpenAI-compatible base URL, API key and model ID, native provider SDKs, code snippets. Not for creating provider accounts (that is models.md).
---

The AI Gateway exposes an **OpenAI-compatible endpoint** for all configured models. It can also **proxy requests for native provider SDKs** (Google Gen AI, Anthropic, boto3/Bedrock etc). In addition, the Anthropic `/messages` endpoint works for Claude models on Anthropic, Claude Platform on AWS, AWS Bedrock, Google Vertex, Azure AI Foundry and Databricks, and for virtual models whose `model_types` include `chat`.

## Integrating with Any OpenAI-Compatible Library/Framework

Any tool, library, or framework that supports OpenAI-compatible APIs can integrate by setting three values:

| Parameter   | Value                                                                              |
| ----------- | ---------------------------------------------------------------------------------- |
| `baseURL`   | `manifest.url` of the `isDefault: true` installation from `list_gateway_installations` — never a hardcoded URL |
| `apiKey`    | TrueFoundry API Key (PAT or VAT)                                                  |
| `model`     | Model ID in `providerAccount/modelName` format (e.g. `openai-main/gpt-4o-mini`)   |

All three values are available in the **Code Snippets** tab of the Playground, or you can generate them with `generate_multi_lang_code_snippets` (`model` required as `accountName/modelName`; optional `inference_type` must be one of the model's `model_types`). For chat models it returns only OpenAI-compatible snippets. For Google Gen AI, Anthropic, boto3 or `langchain_aws`, use the Native SDK Support docs page. You will find instructions to integrate for most of the popular tools/libraries/frameworks in the docs. If none exists, use OpenAI compatibility; it works wherever the tool lets you set the base URL.

Docs: https://www.truefoundry.com/docs/ai-gateway/making-llm-requests-via-gateway

## Native Provider SDK Support

For native SDKs (Google Gen AI, Anthropic, boto3 Bedrock etc), the Gateway provides dedicated proxy endpoints. Tracing, cost tracking, and rate/budget limits work across all of them. Routing configuration (virtual models) does not work through the Google Gen AI SDK, boto3 or `langchain_aws`.

Docs: https://www.truefoundry.com/docs/ai-gateway/native-sdk-support

## External Integrations (IDEs, Agent Frameworks, Apps, Observability)

When trying to integrate with external tools:
 - Use `search_docs` tool directly. Limit to 2 search attempts — results beyond that are unlikely to surface anything new.
   - Judge relevance from the excerpts alone; only extract full page content when the excerpt clearly matches.
 - Not all integrations have dedicated guides in the docs. If no guide is found, fall back to the OpenAI Compatibility or Native SDK Support approaches above. Native SDK proxying is only available for certain providers.

Pre-built integration guides exist for coding assistants (Cursor, Claude Code, GitHub Copilot, Cline, etc.), agent frameworks (LangChain, CrewAI, Pydantic AI, OpenAI Agents SDK, etc.), applications (n8n, Dify, Open WebUI, etc.), and observability platforms (Langfuse, Arize, etc.).

Search terms: "integrate with <toolname / frameworkname / applicationname / observabilityname>"
