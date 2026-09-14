# Connecting providers

Choose **Connect → Provider preset**, supply your own key (or environment variable), and save to discover models. Local server URLs are editable examples; use the actual port your runtime listens on. Choose a chat-capable model from discovery or enter its exact ID. No account, model, credential, or machine is preconfigured.

Presets cover Ollama, LM Studio, llama.cpp/vLLM, OpenAI Responses, OpenAI Chat Completions, Anthropic, Google Gemini, Cohere, Groq, OpenRouter, DeepSeek, and Together AI. Custom endpoints can use any of the six supported protocols. All text adapters participate in the same proposal, peer-review, and unified-answer workflow; shared MCP context remains available.

| Protocol | Base URL convention | Runtime options |
| --- | --- | --- |
| Ollama | Server root | num_ctx, num_predict, num_gpu, temperature, top_p, top_k, think, keep_alive |
| OpenAI Chat Completions | API prefix, usually /v1 | max_tokens, max_completion_tokens, temperature, top_p; provider-specific top_k, reasoning_effort, reasoning_format, thinking_budget_tokens |
| OpenAI Responses | API prefix, usually /v1 | max_output_tokens, temperature, top_p, reasoning |
| Anthropic | /v1 prefix | max_tokens (default 4096), temperature, top_p, top_k, stop_sequences |
| Google Gemini | /v1beta prefix | maxOutputTokens, temperature, topP, topK, stopSequences |
| Cohere | Server root | max_tokens, temperature, p, k, stop_sequences, seed |

Options go in the existing Runtime options JSON field. Only use settings supported by your chosen model. Responses requests set store=false and collect public output text; incomplete responses are reported as errors. Cohere uses v2 chat and v1 chat-filtered model discovery with pagination. Presets are available only when adding a connection, to avoid replacing an existing endpoint's credentials accidentally.

This is text conversation support. Image/audio generation, embeddings, provider-hosted tool execution, AWS Bedrock signing, and Google Vertex service-account authentication are not implemented. Compatible services can differ in model capabilities and accepted options. Discovery may return non-chat models on OpenAI-compatible services; select a chat model. Native Gemini and Anthropic discovery currently reads the first page. A manual model ID works when discovery is unavailable.

## Protocol references

- [OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Cohere Chat](https://docs.cohere.com/reference/chat) and [model listing](https://docs.cohere.com/reference/list-models)
- [Groq compatibility](https://console.groq.com/docs/openai)
- [OpenRouter setup](https://openrouter.ai/docs/quickstart)
- [DeepSeek setup](https://api-docs.deepseek.com/)
- [Together compatibility](https://docs.together.ai/docs/inference/openai-compatibility)

Protocol fixtures verify request paths, credentials, message history, public-text extraction, incomplete-response rejection, discovery pagination, and generation options. They do not establish live access to every cloud provider or model; users need their own credentials and account access.
