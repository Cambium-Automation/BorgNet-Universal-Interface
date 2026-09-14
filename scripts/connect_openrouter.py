#!/usr/bin/env python3
"""Connect OpenRouter to a running BorgNet workspace. Standard library only."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, headers, body=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={**headers, 'Content-Type': 'application/json'})
    try:
        with opener.open(req, timeout=30) as response:
            raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ValueError('Response exceeded the size limit.')
            return json.loads(raw)
    except urllib.error.HTTPError as error:
        # Never echo provider bodies or authentication headers.
        raise ValueError(f'Request returned HTTP {error.code}. Check the API key, server and selected model.') from None
    except urllib.error.URLError:
        raise ValueError('Connection failed. Check Internet access and that BorgNet is running.') from None


def connection_payload(existing, key, model, allow_paid):
    fields = {'id', 'kind', 'url', 'purpose', 'model', 'enabled', 'key_env',
              'ssh', 'options', 'model_options', 'timeout', 'cli_provider', 'cli_agent'}
    payload = {k: v for k, v in existing.items() if k in fields}
    payload.update(kind='openai', url='https://openrouter.ai/api/v1', model=model,
                   enabled=True, key_env='', api_key=key, ssh=None,
                   options={**existing.get('options', {}), 'free_only': not allow_paid})
    payload.setdefault('purpose', 'General chat, coding, reasoning and collaboration through OpenRouter.')
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, help='BorgNet data directory, if not the default')
    parser.add_argument('--port', type=int, default=7337)
    parser.add_argument('--model', default='openrouter/free')
    parser.add_argument('--allow-paid', action='store_true', help='Explicitly allow paid model selection')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    if not args.allow_paid and args.model != 'openrouter/free' and not args.model.endswith(':free'):
        parser.error('Choose openrouter/free or a :free model, or explicitly pass --allow-paid.')
    roots = [args.data_dir] if args.data_dir else ([Path(os.environ['BORGNET_DATA_DIR'])]
        if os.environ.get('BORGNET_DATA_DIR') else [Path.home() / 'Library/Application Support/BorgNet', Path.home() / '.borgnet'])
    base = f'http://127.0.0.1:{args.port}'
    state = None
    for root in roots:
        session_file = root.expanduser() / 'browser-session.json'
        if not session_file.is_file():
            continue
        session = json.loads(session_file.read_text())['token']
        headers = {'X-BorgNet-Session': session}
        try:
            state = request(base + '/api/state', headers)
            break
        except ValueError:
            continue
    if state is None:
        raise ValueError('Start BorgNet first, or specify its --data-dir and --port.')
    key = os.environ.get('OPENROUTER_API_KEY') or getpass.getpass('OpenRouter API key (hidden): ').strip()
    if not key:
        raise ValueError('An OpenRouter API key is required.')
    request('https://openrouter.ai/api/v1/key', {'Authorization': 'Bearer ' + key})
    matches = [c for c in state['connections'] if c.get('url') == 'https://openrouter.ai/api/v1'
               and c.get('kind') == 'openai' and not c.get('ssh')]
    if len(matches) > 1:
        raise ValueError('Multiple OpenRouter connections exist. Edit the intended connection in BorgNet instead.')
    headers['X-BorgNet-Token'] = state['token']
    result = request(base + '/api/connections', headers,
                     connection_payload(matches[0] if matches else {}, key, args.model, args.allow_paid))
    print('OpenRouter connected for chat, coding, reasoning and collaboration.')
    print('Model:', args.model)
    print('Paid models allowed.' if args.allow_paid else 'Free-model restriction enabled.')
    try:
        catalog = request(base + '/api/connections/' + result['id'] + '/discover', headers, {})
        print('Discovered models:', len(catalog['models']))
    except ValueError:
        print('Connection saved; discovery unavailable. Use Refresh connections later.')
    print('Reload BorgNet to see the connection. The key is stored in its local secrets file.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        sys.exit(str(error))
    except (KeyboardInterrupt, EOFError):
        sys.exit('Cancelled.')
