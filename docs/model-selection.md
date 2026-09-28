# Prompt-based model selection

Choose **Model selector** in the composer to configure a selector, then choose
**Jev routes · one model** under Response mode when Jev is configured. Each request selects one of the
enabled connections with a configured model. Discovered but unselected model IDs
are not candidates. Set each connection's purpose, capability notes, and usable
runtime context window in Edit connection. Capability notes should state verified
strengths and limits; an unknown field should stay unknown rather than guessed.

Selectors supported:

- **Ollama:** a native JSON schema response.
- **OpenAI-compatible:** a forced `select_model` function call. The endpoint and
  model must support tool calls; a plain chat-only gateway will report an error.
- **Jev:** TypeSafe's native `/v1/systemone` Choice API, using `jev-latest` by
  default. Save a TypeSafe key in this dialog or set `TYPESAFE_API_KEY` in the
  service environment. Keys use BorgNet's existing separate local secret store.
  Jev Terminal's credentials are not automatically copied.

The selector prioritizes expected answer quality, using each candidate's model
identity, purpose, capability notes, context window, protocol, and BorgNet's
current host-tool grants. The tool fields distinguish commands, isolated browser
interaction, Mac app connectors, installed Blender/VS Code/Cura workflows, and
visual desktop control that has macOS consent. A user capability note cannot
override a disabled tool grant. API endpoint function-call support is shown as
unknown unless separately verified; the grant alone does not prove protocol support.
It also sees
the size of the current request, reference data, and recent conversation so it
can account for context fit. This is not a benchmark or guarantee. The selected connection keeps
its existing permissions and runtime options. The selector itself only returns a
choice; its output cannot enable tools, modify permissions, or nominate an unknown
connection. Jev's confidence is a classification judgment, not measured answer
quality.

The selector receives the current prompt (up to 12,000 characters), candidate
model descriptions (purpose up to 800 characters and capability notes up to
1,200 characters each), declared context windows, up to 2,000 characters of
attached reference data, and the last three request excerpts (500 characters
each). It sees aggregate lengths for the reference and recent conversation;
character counts are not exact token counts.
The answering model receives the full selected reference data and up to eight
previous conversation turns, including successful responses from a previous
selected model. Selection adds an inference request and its provider costs/latency.
A single candidate skips selector inference.

Selection and its reason appear in the response group and saved conversation
history. Invalid output, an uncertain choice, timeout, or an unavailable selector
stops the request with an error. No silent model substitution or automatic retry
occurs. The interface shows a routing state while the selector runs, then only
the chosen answer model. Other answer models are not contacted. Independent
answers and collaborative review/debate remain separate modes.

Protocol reference: https://docs.typesafe.ai/api
