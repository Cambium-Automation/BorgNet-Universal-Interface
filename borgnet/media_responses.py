"""Public provider text and outcome metadata, never raw response payloads."""
from contextvars import ContextVar
import re

responses = ContextVar('media_responses', default=None)


def redact(text, secrets=()):
    text = str(text)
    for secret in secrets:
        if isinstance(secret, str) and secret:
            text = text.replace(secret, '[redacted]')
    text = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{15,})\b', '[redacted]', text)
    text = re.sub(r'(?i)\bBearer\s+[^\s"\'<>]+', 'Bearer [redacted]', text)
    text = re.sub(r'https?://[^\s<>"\']+', '[URL omitted]', text)
    return text


def public_response(data, secrets=()):
    messages, codes = [], []
    def objects(value):
        return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []
    def mapping(value):
        return value if isinstance(value, dict) else {}
    if not isinstance(data, dict):
        return {'messages': [], 'codes': [], 'truncated': False}
    def message(value):
        if isinstance(value, str) and value.strip():
            messages.append(redact(value, secrets))
    def code(value):
        if isinstance(value, (str, int, bool)):
            codes.append(redact(value, secrets))
    error = data.get('error')
    if isinstance(error, dict):
        message(error.get('message')); code(error.get('code')); code(error.get('type'))
    elif isinstance(error, str):
        message(error)
    message(data.get('message')); message(data.get('refusal'))
    if data.get('respect_moderation') is False:
        code('respect_moderation=false')
    feedback = data.get('promptFeedback') or {}
    if isinstance(feedback, dict):
        code(feedback.get('blockReason')); message(feedback.get('blockReasonMessage'))
    for candidate in objects(data.get('candidates')):
        code(candidate.get('finishReason'))
        for part in objects(mapping(candidate.get('content')).get('parts')):
            if not part.get('thought'):
                message(part.get('text'))
    for choice in objects(data.get('choices')):
        code(choice.get('finish_reason'))
        reply = mapping(choice.get('message'))
        message(reply.get('refusal'))
        content = reply.get('content')
        if isinstance(content, str):
            message(content)
        elif isinstance(content, list):
            for part in objects(content):
                if part.get('type') == 'text':
                    message(part.get('text'))
    for item in objects(data.get('data')):
        message(item.get('revised_prompt'))
    video = data.get('video') or {}
    if isinstance(video, dict) and video.get('respect_moderation') is False:
        code('respect_moderation=false')
    result = data.get('response') or {}
    if isinstance(result, dict):
        result = result.get('generateVideoResponse') or result
        if isinstance(result, dict):
            for reason in (result.get('raiMediaFilteredReasons') or []) if isinstance(result.get('raiMediaFilteredReasons'), list) else []:
                message(reason)
            if result.get('raiMediaFilteredCount'):
                code('raiMediaFilteredCount=' + str(result['raiMediaFilteredCount']))
    for generation in objects(data.get('generations')):
        if generation.get('censored'):
            code('worker_censored=true')
        for meta in objects(generation.get('gen_metadata')):
            code(meta.get('type')); code(meta.get('value'))
    messages = list(dict.fromkeys(messages))
    codes = list(dict.fromkeys(codes))
    truncated = sum(map(len, messages)) > 32768 or len(messages) > 32 or len(codes) > 32 or any(len(x) > 300 for x in codes)
    remaining = 32768
    kept = []
    for text in messages[:32]:
        if remaining <= 0:
            break
        kept.append(text[:remaining]); remaining -= len(kept[-1])
    return {'messages': kept, 'codes': [x[:300] for x in codes[:32]], 'truncated': truncated}


def capture(data, secrets=()):
    reply = public_response(data, secrets)
    target = responses.get()
    if target is not None and (reply['messages'] or reply['codes']) and reply not in target:
        if len(target) < 16:
            target.append(reply)
        else:
            target[-1]['truncated'] = True
    return reply


class ProviderResponseError(ValueError):
    def __init__(self, message, reply, status=None):
        super().__init__(message)
        self.reply, self.status = reply, status
