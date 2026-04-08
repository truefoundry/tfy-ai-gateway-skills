---
name: integrations
description: Integrate AI Gateway models with any OpenAI-compatible tool, native provider SDK, or third-party framework.
---

The AI Gateway exposes an **OpenAI-compatible endpoint** for all configured models. In addition, it can **proxy requests for native provider SDKs** (Google Gen AI, Anthropic, boto3/Bedrock etc). In addition, all anthropic model (on anthropic/vertex/bedrock/azure-foundry) are available with Anthropic /messages compatible endpoint.

## Integrating with Any OpenAI-Compatible Library/Framework

Any tool, library, or framework that supports OpenAI-compatible APIs can integrate by setting three values:

| Parameter   | Value                                                                              |
| ----------- | ---------------------------------------------------------------------------------- |
| `baseURL`   | Gateway Base URL (`https://gateway.truefoundry.ai` for SaaS, or self-hosted URL)   |
| `apiKey`    | TrueFoundry API Key (PAT or VAT)                                                  |
| `model`     | Model ID in `providerAccount/modelName` format (e.g. `openai-main/gpt-4o-mini`)   |

All three values are available in the **Code Snippets** tab of the Playground. You will find instructions to integrate for most of the popular tools/libraries/frameworks in the docs. But if it is not available, stick to basics. You can integrate using OpenAI Compatibility. You just need to ensure the target integration allows you to set the baseURL or not.

Docs: https://www.truefoundry.com/docs/ai-gateway/making-llm-requests-via-gateway

## Native Provider SDK Support

For native SDKs (Google Gen AI, Anthropic, boto3 Bedrock etc), the Gateway provides dedicated proxy endpoints. Tracing, cost tracking, and rate/budget limits work across all of them.

Docs: https://www.truefoundry.com/docs/ai-gateway/native-sdk-support

## External Integrations (IDEs, Agent Frameworks, Apps, Observability)

When trying to integrate with external tools:
 - Use search_true_foundry_docs tool directly (dont make more than 2 attempts).
   - You can figure out if the returned results are relevant just by the excerpts. You should NOT try to extract the content if page does not seem relevant.
 - It is normal that a new integration guide is not available in the docs. In that case, agent should try to figure out integration using the OpenAI Compatibility or Native SDK Support. Note: Native SDK will work only for certain providers only

Pre-built integration guides exist for coding assistants (Cursor, Claude Code, GitHub Copilot, Cline, etc.), agent frameworks (LangChain, CrewAI, Pydantic AI, OpenAI Agents SDK, etc.), applications (n8n, Dify, Open WebUI, etc.), and observability platforms (Langfuse, Arize, etc.).