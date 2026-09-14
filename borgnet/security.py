"""Loopback browser isolation and bounded request bodies."""
import secrets
from urllib.parse import urlsplit
from starlette.datastructures import Headers, QueryParams
from starlette.responses import JSONResponse

LIMIT = 1_000_000
HEADERS = {
    'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
    'Cache-Control': 'no-store', 'Cross-Origin-Resource-Policy': 'same-origin',
    'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'",
}


class LocalBoundary:
    def __init__(self, app, session, media, token):
        self.app, self.session, self.media, self.token = app, session, media, token

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        async def reject(message, status):
            await JSONResponse({'error': message}, status_code=status, headers=HEADERS)(scope, receive, send)
        host = headers.get('host', '')
        try:
            parsed = urlsplit('http://' + host)
            valid = parsed.hostname in {'127.0.0.1', 'localhost', '::1'} and not parsed.username and not parsed.password and not parsed.path and not parsed.query and not parsed.fragment
            parsed.port
        except ValueError:
            valid = False
        if not valid:
            return await reject('BorgNet serves loopback hosts only', 403)
        if headers.get('origin') not in (None, f"{scope['scheme']}://{host}"):
            return await reject('Cross-origin access denied', 403)
        # Different localhost ports are different origins, even if classified same-site.
        if headers.get('sec-fetch-site') in {'cross-site', 'same-site'}:
            return await reject('Cross-origin access denied', 403)
        path = scope['path']
        if path.startswith('/api/'):
            authorized = secrets.compare_digest(headers.get('x-borgnet-session', '').encode('utf-8'), self.session.encode('ascii'))
            is_media = scope['method'] in {'GET', 'HEAD'} and (
                path.startswith('/api/images/imagegen/images/') or
                (path.startswith('/api/videos/') and path.endswith('/content')))
            if is_media:
                authorized |= secrets.compare_digest(QueryParams(scope.get('query_string', b'')).get('media_token', '').encode('utf-8'), self.media.encode('ascii'))
            if not authorized:
                return await reject('Open the private launch link printed by borgnet serve to unlock this workspace.', 401)
        if scope['method'] not in {'GET', 'HEAD', 'OPTIONS'}:
            if not secrets.compare_digest(headers.get('x-borgnet-token', '').encode('utf-8'), self.token.encode('ascii')):
                return await reject('Refresh this page before making changes', 403)
        if scope['method'] not in {'GET', 'HEAD'}:
            try:
                declared = int(headers.get('content-length', '0'))
                if declared < 0:
                    raise ValueError()
            except ValueError:
                return await reject('Invalid Content-Length', 400)
            if declared > LIMIT:
                return await reject('Request too large', 413)
            body = bytearray()
            more = True
            while more:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > LIMIT:
                    return await reject('Request too large', 413)
                more = message.get('more_body', False)
            delivered = False
            original_receive = receive
            async def receive_body():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await original_receive()
            receive = receive_body
        async def protected_send(message):
            if message['type'] == 'http.response.start':
                extra = [(k.lower().encode(), v.encode()) for k, v in HEADERS.items()]
                message['headers'] = list(message.get('headers', [])) + extra
            await send(message)
        await self.app(scope, receive, protected_send)
