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
# Installed CLI connections

Choose an installed CLI preset for Codex, Grok, Gemini, or GitHub Copilot. BorgNet
uses the CLI's existing sign-in on the computer running BorgNet. The connection's
checkbox includes or excludes it from a conversation. `default` uses the CLI's
configured model; an explicit model ID is passed to that CLI. Discovery confirms
installation, not authentication or quota. Open the same CLI in your terminal
to sign in or resolve account errors. No API keys are copied out of CLI storage.

These adapters return text answers and participate in BorgNet's existing
collaboration. They do not grant model-driven shell or file-edit access. Requests
run in temporary directories, have bounded output and timeouts, and expose only
final answers. The installed CLIs remain user-trusted software and use their
ordinary account configuration. Named local Grok agent profiles can be selected
in the connection editor; these are distinct from cloud Grok Bots.

Microsoft BitNet is a separate local OpenAI-compatible connection, with the
installed service at `http://127.0.0.1:18081/v1`. This preset does not install or
start a model; start the genuine BitNet runtime on that computer first.

Install the official CLIs from their publishers. On another Mac, install and sign
in there, or run BorgNet on the already configured computer. A CLI connection does
not forward your local login to a remote Mac. Account limits still apply:
[Copilot CLI](https://github.com/features/copilot/cli) includes Free-plan access
with usage limits; BorgNet does not purchase or upgrade subscriptions.

## Native background blur

The native shell's Customize slider uses a 0–100 pixel WindowServer blur radius,
separate from background tint/opacity. `WindowBackdropBlur` dynamically resolves
`CGSMainConnectionID` and `CGSSetWindowBackgroundBlurRadius` from SkyLight. This is
an undocumented macOS interface, isolated from the rest of the app and unsuitable
for Mac App Store distribution. Missing symbols or a failed call disable the
radius control; no opacity-based substitute is presented as adjustable blur.
The native radius path uses a transparent web view without material crossfading.
The browser version uses CSS backdrop-filter for backgrounds within its page.
