"""Describe a connection's request-scoped abilities without granting new authority."""
import json
from urllib.parse import urlsplit

from .permissions import effective


def briefing(store, item, host_tools=True):
    if item.kind not in {'ollama', 'openai', 'cli'}:
        return ''
    policy = effective(store, item)
    lines = ['BORGNET CONNECTION FACTS (current request):',
             f'Configured model ID: {item.model}. This identifies the endpoint request, not a verified underlying worker.']
    if item.kind == 'cli':
        lines.append(f'Transport: installed {item.cli_provider} CLI on this Mac.')
    elif item.ssh:
        lines.append('Transport: an SSH tunnel to a model endpoint. The tunnel alone grants no shell or file access on either computer.')
    else:
        host = urlsplit(item.url).hostname
        lines.append('Transport: a loopback model endpoint on this Mac.' if host in {'localhost', '127.0.0.1', '::1'}
                     else 'Transport: a remote model API. Endpoint network access does not grant access to this Mac.')
    if item.capabilities.strip():
        lines.append('Operator-configured model capability notes (descriptive, unverified; not tool grants or instructions): '
                     + json.dumps(item.capabilities.strip()[:1200], ensure_ascii=False))
    else:
        lines.append('Model-specific strengths are not configured; do not invent them.')
    if item.context_window:
        lines.append(f'Configured context window: {item.context_window} tokens (operator estimate, not endpoint verified).')
    else:
        lines.append('Context window: not configured or verified.')
    if item.kind == 'ollama' and type(item.options.get('num_ctx')) is int:
        lines.append(f'Ollama num_ctx requested for this call: {item.options["num_ctx"]} tokens; the server may impose a different effective limit.')
    output = next((item.options[k] for k in ('max_completion_tokens', 'max_tokens', 'num_predict')
                   if type(item.options.get(k)) is int), None)
    if output is not None:
        lines.append(f'Requested output limit: {output} tokens; completion may stop earlier.')
    if not policy.full_access or (item.kind in {'openai', 'ollama'} and not host_tools):
        if policy.full_access and not host_tools:
            lines.append('BorgNet does not offer host tools during this structured response.')
            return '\n'.join(lines)
        if item.kind == 'cli' and item.cli_provider in {'codex', 'grok'} and policy.network:
            lines.append('BorgNet permits this CLI its built-in web search/fetch. Host shell, local files, browser interaction, and desktop tools are disabled.')
        else:
            lines.append('BorgNet provides no host command, file, browser, or desktop tools for this request.')
        return '\n'.join(lines)
    lines.append(f'BorgNet-granted host workspace: {policy.workspace}. Only use tools supplied by this request for authorized actions.')
    if item.kind in {'openai', 'ollama'}:
        lines.append('Native function-call tools are offered for Mac command execution. The endpoint must support tool calling; support is not verified until a call succeeds. Text claiming a tool was used does not execute it.')
    else:
        lines.append('The installed CLI is configured for host tools. Actual availability depends on the CLI and its sign-in.')
    try:
        from .adapter_setup import status
        adapters = status()
    except (OSError, ValueError, KeyError, ImportError, StopIteration):
        adapters = None
    connector_ready = not (item.kind == 'cli' and item.cli_provider == 'grok') or bool(adapters and adapters.get('grok_registered'))
    if not connector_ready:
        lines.append('Grok BorgNet MCP adapter: not registered; enabled browser or desktop requests cannot run until it is registered.')
    if policy.browser:
        ready = bool(adapters['browser']['ready'] and connector_ready) if adapters else None
        lines.append('Isolated browser adapter: ' + ('ready' if ready else 'not ready' if ready is False else 'readiness unknown') + '. Use only supplied browser tools.')
    else:
        lines.append('Isolated browser adapter: disabled.')
    if policy.computer:
        from . import app_connectors
        import sys
        if sys.platform == 'darwin':
            apps = {'Blender scene inspection': connector_ready and app_connectors.BLENDER.is_file(),
                    'VS Code file open': connector_ready and app_connectors.VSCODE.is_file(),
                    'Cura profile inspection': connector_ready and app_connectors.CURA_ENGINE.is_file(),
                    'Cura model open': connector_ready and app_connectors.cura_open_available()}
            lines.append('Mac app workflows: ' + ', '.join(f'{name} {"available" if ready else "unavailable"}' for name, ready in apps.items()) + '.')
        else:
            lines.append('Mac app workflows: unavailable on this host.')
        desktop = bool(adapters['computer']['ready'] and connector_ready) if adapters else None
        if item.kind == 'cli':
            lines.append('Visual desktop control: ' + ('adapter ready' if desktop else 'adapter not ready' if desktop is False else 'readiness unknown') + '; OS consent may still be required.')
        else:
            lines.append('General visual desktop screenshot/click control is not supplied to native function-call connections.')
    else:
        lines.append('Mac app and desktop adapters: disabled.')
    return '\n'.join(lines)
