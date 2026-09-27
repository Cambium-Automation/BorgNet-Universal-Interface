# Direct chat with one model

In the BorgNet composer, set **Response mode** to **Chat with one model**.
Use the adjacent **Model** menu to pick an enabled connection, then send a
message. A new conversation starts with **New conversation**. Follow-up
messages in a conversation keep the selected model's previous answers as
context. Switching models only sends that model's own prior answers; it does
not silently hand another model's answer to it.

Expand the response bar to inspect each model's live answer. Local Ollama and
loopback or SSH OpenAI-compatible endpoints also show a **Model-emitted
reasoning** panel when the endpoint sends an explicit reasoning stream. The
panel shows the model's own emitted text, which may be incomplete or absent;
it is separate from the answer and is not saved in conversation history.
For a direct OpenAI-compatible loopback connection, enable the trusted local
reasoning option in Edit connection. SSH connections to a loopback model server
and Ollama connections do not need that extra switch.
Cloud-provider private reasoning and tool arguments are not shown. When a
local endpoint exposes no reasoning stream, the panel says so after the
response completes.

Each connection's expanded card shows its declared capabilities and configured
context window. These are configuration, not verified benchmarks. BorgNet
also briefs the model about the tools actually granted and ready for that
request, so a local model does not have to guess what the host can do.

Local workers registered as separate connections appear individually in the
Model menu. An aggregate or router is a separate connection and may have a
different effective context limit. Set each connection's context window to
its tested runtime limit; an advertised model limit does not prove the server
can use it. An SSH connection reaches only the endpoint you configured and
does not install or start model weights automatically.

Selecting an API or CLI connection still uses that connection's own account,
permissions and provider limits. A configured model may return an access or
quota error; direct chat reports it without switching connections.
