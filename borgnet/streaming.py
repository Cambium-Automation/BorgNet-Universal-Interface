"""Bounded public-text streaming with a separate local reasoning display channel."""
import codecs
import json
import re
from contextvars import ContextVar
from urllib.parse import urlsplit

listener = ContextVar('borgnet_stream_listener', default=None)
reasoning_listener = ContextVar('borgnet_reasoning_listener', default=None)
MAX_BYTES = 8_000_000
MAX_REASONING_CHARS = 48_000


def reasoning_eligible(item):
    """A loopback OpenAI API can be a cloud proxy, so require explicit trust."""
    loopback = {'localhost', '127.0.0.1', '::1'}
    if item.kind not in {'ollama', 'openai'}:
        return False
    if item.ssh:
        return item.ssh.remote_host in loopback
    if urlsplit(item.url).hostname not in loopback:
        return False
    return item.kind == 'ollama' or item.options.get('show_local_reasoning') is True


def context_error(raw):
    """Recognize only numeric context diagnostics; never echo arbitrary provider data."""
    try:
        detail = json.loads(raw).get('detail', '')
    except (ValueError, AttributeError):
        return None
    if isinstance(detail, str) and re.fullmatch(
            r'Context exceeds \d{1,9} tokens: prompt=\d{1,9}, reserved output=\d{1,9}\. '
            r'Reduce context/history or max_tokens; nothing was truncated\.', detail):
        return detail
    return None


def public_delta(kind, event):
    if kind == 'ollama':
        return event.get('message', {}).get('content', '')
    if kind == 'openai':
        choices = event.get('choices') or []
        content = choices[0].get('delta', {}).get('content', '') if choices else ''
        if isinstance(content, list):
            return ''.join(x.get('text', '') for x in content if x.get('type') == 'text')
        return content or ''
    if kind == 'responses':
        return event.get('delta', '') if event.get('type') == 'response.output_text.delta' else ''
    if kind == 'anthropic':
        delta = event.get('delta', {})
        if event.get('type') == 'content_block_delta' and delta.get('type') == 'text_delta':
            return delta.get('text', '')
    if kind == 'gemini':
        candidates = event.get('candidates') or []
        return ''.join(p.get('text', '') for p in candidates[0].get('content', {}).get('parts', []) if not p.get('thought')) if candidates else ''
    if kind == 'cohere' and event.get('type') == 'content-delta':
        return event.get('delta', {}).get('message', {}).get('content', {}).get('text', '')
    return ''


def reasoning_delta(kind, event):
    """Only explicit local-model reasoning fields, never content or tool arguments."""
    if kind == 'ollama':
        value = (event.get('message') or {}).get('thinking', '')
    elif kind == 'openai':
        choices = event.get('choices') or []
        delta = (choices[0].get('delta') or {}) if choices else {}
        value = delta.get('reasoning_content', delta.get('reasoning', ''))
    else:
        return ''
    return value if isinstance(value, str) else ''


def complete_reasoning(kind, data):
    if not isinstance(data, dict):
        return ''
    if kind == 'ollama':
        message = data.get('message') or {}
    elif kind == 'openai':
        choices = data.get('choices') or []
        message = (choices[0].get('message') or {}) if choices else {}
    else:
        return ''
    if not isinstance(message, dict):
        return ''
    value = message.get('thinking', '') if kind == 'ollama' else message.get('reasoning_content', message.get('reasoning', ''))
    return value if isinstance(value, str) else ''


async def stream_request(client, kind, method, url, payload, headers, emit, emit_reasoning=None):
    payload = dict(payload)
    if kind == 'gemini':
        url = url.replace(':generateContent', ':streamGenerateContent') + '?alt=sse'
    else:
        payload['stream'] = True
    text, size, pending, reasoning_size = [], 0, '', 0
    decoder = codecs.getincrementaldecoder('utf-8')()
    completed = False
    async with client.stream(method, url, json=payload, headers=headers) as response:
        if not response.is_success:
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk[:4097-len(raw)])
                if len(raw) > 4096:
                    break
            detail = context_error(raw) if len(raw) <= 4096 else None
            if detail:
                raise ValueError(detail)
            raise ValueError(f'Provider streaming request failed (HTTP {response.status_code}); check endpoint support, model access and quota')
        if response.headers.get('content-type', '').split(';')[0] == 'application/json':
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_BYTES: raise ValueError('Provider response exceeds the 8 MB limit')
            data = json.loads(raw)
            if emit_reasoning:
                reason = complete_reasoning(kind, data)
                if reason:
                    await emit_reasoning(reason[:MAX_REASONING_CHARS])
                    if len(reason) > MAX_REASONING_CHARS:
                        await emit_reasoning('\n[Model reasoning display truncated.]')
            return data
        async def consume(line):
            nonlocal completed, reasoning_size
            line = line.strip()
            if not line or line.startswith(('event:', ':', 'id:', 'retry:')):
                return
            if line.startswith('data:'):
                line = line[5:].strip()
            if line == '[DONE]':
                completed = True
                return
            try:
                event = json.loads(line)
            except ValueError:
                raise ValueError('Provider returned an invalid streaming event') from None
            if not isinstance(event, dict):
                raise ValueError('Provider returned an invalid streaming event')
            if event.get('error') or event.get('type') in {'error','response.failed','response.incomplete'}:
                raise ValueError('Provider stream failed or was incomplete')
            delta = public_delta(kind, event)
            if not isinstance(delta, str):
                raise ValueError('Provider returned invalid public text')
            if delta:
                text.append(delta)
                await emit(delta)
            if emit_reasoning and reasoning_size < MAX_REASONING_CHARS:
                reasoning = reasoning_delta(kind, event)
                if reasoning:
                    remaining = MAX_REASONING_CHARS - reasoning_size
                    shown = reasoning[:remaining]
                    reasoning_size += len(shown)
                    if shown:
                        await emit_reasoning(shown)
                    if len(reasoning) > remaining:
                        await emit_reasoning('\n[Model reasoning display truncated.]')
            if event.get('done') or event.get('type') in {'message_stop','message-end','response.completed'}:
                completed = True
            if kind == 'gemini' and any(c.get('finishReason') for c in event.get('candidates', [])):
                completed = True
            if kind == 'openai' and any(c.get('finish_reason') is not None for c in event.get('choices', [])):
                completed = True
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('Provider stream exceeds the 8 MB limit')
            pending += decoder.decode(chunk)
            while '\n' in pending:
                line, pending = pending.split('\n', 1)
                await consume(line)
        pending += decoder.decode(b'', final=True)
        if pending.strip():
            await consume(pending)
    if not completed:
        raise ValueError('Provider stream ended before completion; partial text is not a completed answer')
    answer = ''.join(text)
    # Preserve existing final-answer validation in Providers.chat.
    return {
        'ollama': {'message': {'content': answer}},
        'openai': {'choices': [{'message': {'content': answer}}]},
        'responses': {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':answer}]}]},
        'anthropic': {'content':[{'type':'text','text':answer}]},
        'gemini': {'candidates':[{'content':{'parts':[{'text':answer}]}}]},
        'cohere': {'finish_reason':'COMPLETE','message':{'content':[{'type':'text','text':answer}]}},
    }[kind]
