"""Shared, persistent broadcast state and live OBS screen server. Python 3.12+."""
import copy
import json
import os
from pathlib import Path
import threading
import time
from urllib.request import urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from respawn import summarize, broadcast_patch
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DEFAULTS = json.loads((ROOT / 'defaults.json').read_text())
SCREENS = tuple(DEFAULTS['screens'])
PUBLIC_URL = os.environ.get('APEX_PUBLIC_URL', 'https://apex.praxidike.space').rstrip('/')
STATE_FILE = Path(os.environ.get('APEX_STATE_FILE', ROOT / 'data/state.json'))
LOCK = threading.RLock()


def merge(base, patch):
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def validate(state):
    if not isinstance(state, dict) or set(state) != {'global', 'screens'}:
        raise ValueError('State must contain global and screens objects')
    if not isinstance(state['global'], dict) or not isinstance(state['screens'], dict):
        raise ValueError('global and screens must be objects')
    if set(state['screens']) != set(SCREENS):
        raise ValueError('Keep all six known screen names')
    known = {key for settings in DEFAULTS['screens'].values() for key in settings} | {'week', 'phase'}
    if set(state['global']) - known:
        raise ValueError('Unknown global setting')
    shared = state['global']
    if 'week' in shared:
        if type(shared['week']) is not int or shared['week'] < 1:
            raise ValueError('week must be a positive integer')
        if not isinstance(shared.get('season'), str) or not shared['season'].strip():
            raise ValueError('Set season together with week')
    if 'statsTokens' in shared and (not isinstance(shared['statsTokens'], list) or any(not isinstance(t, str) for t in shared['statsTokens'])):
        raise ValueError('statsTokens must be a list of token strings')
    if 'phase' in shared and (not isinstance(shared['phase'], str) or not shared['phase'].strip()):
        raise ValueError('phase must be nonempty text')
    for name, settings in state['screens'].items():
        if not isinstance(settings, dict) or set(settings) != set(DEFAULTS['screens'][name]):
            raise ValueError(f'{name}: keep the existing setting names')
        effective = merge(settings, {k:v for k,v in state['global'].items() if k in settings})
        for key, value in effective.items():
            original = DEFAULTS['screens'][name][key]
            if isinstance(original, bool):
                valid = isinstance(value, bool)
            elif isinstance(original, (int, float)):
                valid = isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
            else:
                valid = isinstance(value, type(original))
            if not valid:
                raise ValueError(f'{name}.{key}: incorrect value type or negative number')
        if 'colors' in effective and any(not isinstance(v, str) for v in effective['colors'].values()):
            raise ValueError('Color values must be strings')
    # Reject NaN/Infinity as well as non-JSON data before accepting or persisting.
    json.dumps(state, allow_nan=False)


STATE = merge(DEFAULTS, json.loads(STATE_FILE.read_text())) if STATE_FILE.exists() else copy.deepcopy(DEFAULTS)
# Remove the retired intermission forecast fields from existing saved state.
for key in ('nextLabel', 'nextUp'):
    STATE['screens']['intermission'].pop(key, None)
# Migrate the old uploaded file's token-in-resultsFrom into the weekly variable.
legacy = STATE['screens']['standings']['resultsFrom']
if legacy not in ('manual', 'token'):
    STATE['global'].setdefault('statsTokens', [legacy])
    STATE['screens']['standings']['resultsFrom'] = 'token'
validate(STATE)
SUMMARY_FILE = STATE_FILE.with_name('respawn-summary.json')
SUMMARY = json.loads(SUMMARY_FILE.read_text()) if SUMMARY_FILE.exists() else None
FEED_STATUS = {'lastSuccess': None, 'error': None, 'source': None}



def update_state(patch):
    """Atomically merge a patch; arrays replace arrays. Returns the current state."""
    global STATE
    with LOCK:
        if "global" in patch and not isinstance(patch["global"], dict):
            raise ValueError("global must be an object")
        candidate = merge(STATE, patch)
        for key, value in patch.get("global", {}).items():
            if value is None:
                candidate["global"].pop(key, None)
        validate(candidate)
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = STATE_FILE.with_suffix('.tmp')
        temporary.write_text(json.dumps(candidate, indent=2, allow_nan=False) + '\n')
        temporary.replace(STATE_FILE)
        STATE = candidate
        return copy.deepcopy(STATE)


def effective_settings(name):
    with LOCK:
        settings = STATE['screens'][name]
        shared = STATE['global']
        effective = merge(settings, {k:v for k,v in shared.items() if k in settings})
        if 'week' in shared:
            season = shared['season'].strip()
            week = shared['week']
            phase = shared.get('phase', 'REGULAR SEASON').strip()
            if 'eventLine' in effective:
                effective['eventLine'] = f'{phase} // WEEK {week}'
            if 'sideText' in effective:
                effective['sideText'] = f'COLLEGIATE APEX LEGENDS // {season} // WEEK {week}'
            if name == 'ingame-overlay':
                effective['eventLine'] = f'{season} WEEK {week}'
                if effective['mapName']:
                    effective['eventLine'] += f" // {effective['mapName']}"
        return effective


def ingest_results(payload, source='import'):
    global SUMMARY
    with LOCK:
        settings = effective_settings('standings')
        summary = summarize(payload, settings)
        if source != 'Respawn API' or summary != SUMMARY:
            update_state(broadcast_patch(summary, settings['totalGames']))
        SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SUMMARY_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(summary))
        tmp.replace(SUMMARY_FILE)
        SUMMARY = summary
        FEED_STATUS.update(lastSuccess=time.time(), error=None, source=source)
        return copy.deepcopy(summary)


def current_token():
    with LOCK:
        tokens = STATE['global'].get('statsTokens', STATE['screens']['standings']['statsTokens'])
        return tokens[0].strip() if tokens else ''


def configure_token(token):
    global SUMMARY
    if not isinstance(token, str) or len(token) > 500 or any(c.isspace() for c in token):
        raise ValueError('Token must be text without spaces (or empty to disable polling)')
    with LOCK:
        if token == current_token():
            return
        # Preserve school aliases and adjustments, discard last week's games.
        teams = [{**team, 'games': []} for team in effective_settings('standings')['teams']]
        update_state({'global': {'statsTokens': [token] if token else [], 'mapName': ''},
                      'screens': {'standings': {'resultsFrom': 'manual', 'teams': teams, 'pastedResults': ''},
                                  'stream-ending': {'champion': '', 'rankings': []},
                                  'game-winner': {'teamName': '', 'players': [], 'kills': 0, 'damage': ''}}})
        SUMMARY = None
        SUMMARY_FILE.unlink(missing_ok=True)
        FEED_STATUS.update(lastSuccess=None, error=None, source=None)


def fetch_results(token):
    url = 'https://r5-crossplay.r5prod.stryder.respawn.com/privatematch/?' + urlencode({'token': token})
    with urlopen(url, timeout=15) as response:
        body = response.read(5_000_001)
        if len(body) > 5_000_000:
            raise ValueError('API response exceeds 5 MB')
        return json.loads(body, strict=False)


def poll_once():
    token = current_token()
    if not token:
        return
    try:
        data = fetch_results(token)
        with LOCK:
            if token == current_token():
                ingest_results(data, source='Respawn API')
    except HTTPError as exc:
        with LOCK:
            FEED_STATUS['error'] = f'Respawn HTTP {exc.code}; previous results kept'
    except (URLError, TimeoutError, OSError):
        with LOCK:
            FEED_STATUS['error'] = 'Respawn connection failed; check network access and token. Previous results kept.'
    except (ValueError, TypeError, KeyError, OverflowError):
        with LOCK:
            FEED_STATUS['error'] = 'Respawn response has no usable completed results; previous results kept'


def poll_forever():
    while True:
        poll_once()
        with LOCK:
            interval = max(10, effective_settings('standings')['refreshSeconds'])
        time.sleep(interval)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'screens'), **kwargs)

    def send_data(self, status, data, content_type='application/json'):
        body = data.encode() if isinstance(data, str) else json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/config':
            return self.send_data(200, {'publicBaseUrl': PUBLIC_URL, 'screens': {name: PUBLIC_URL + '/' + name for name in SCREENS}})
        if path == '/api/state':
            with LOCK:
                return self.send_data(200, copy.deepcopy(STATE))
        if path == '/api/results':
            with LOCK:
                return self.send_data(200, {'summary': SUMMARY, 'status': FEED_STATUS, 'tokenConfigured': bool(current_token())})
        if path == '/api/health':
            return self.send_data(200, {'ok': True})
        if path.startswith('/api/screens/'):
            name = path.rsplit('/', 1)[-1]
            if name in SCREENS:
                settings = effective_settings(name)
                if name == 'standings':
                    settings['statsTokens'] = []
                return self.send_data(200, settings)
            return self.send_data(404, {'error': 'Unknown screen'})
        if path in ('/', '/control'):
            return self.send_data(200, (ROOT / 'control.html').read_text(), 'text/html')
        name = path.removeprefix('/').removesuffix('.html')
        if name in SCREENS:
            wrapper = (ROOT / 'live.html').read_text().replace('__SCREEN__', name)
            return self.send_data(200, wrapper, 'text/html')
        if path.startswith('/render/') and path.endswith('.html'):
            name = path[len('/render/'):-5]
            if name not in SCREENS:
                return self.send_data(404, {'error': 'Unknown screen'})
            # Escape HTML-sensitive characters so settings cannot end the script tag.
            effective = effective_settings(name)
            if name == 'standings':
                effective['statsTokens'] = []
            settings = json.dumps(effective, allow_nan=False).replace('<', '\\u003c')
            html = (ROOT / 'screens' / (name + '.html')).read_text()
            html = html.replace('<head>', '<head><base href="/">', 1)
            html = html.replace('<!-- PYTHON_SETTINGS -->', '<script>const SETTINGS = ' + settings + ';</script>')
            return self.send_data(200, html, 'text/html')
        if path.endswith('.html') or path.endswith('/') or path.startswith('/api/'):
            return self.send_data(404, {'error': 'Not found'})
        return super().do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ('/api/results', '/api/respawn/token'):
            return self.send_data(404, {'error': 'Not found'})
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            return self.send_data(403, {'error': 'Cross-origin writes are not allowed'})
        if self.headers.get_content_type() != 'application/json':
            return self.send_data(415, {'error': 'Use application/json'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 5_000_000:
                return self.send_data(413, {'error': 'Body must be between 1 and 5000000 bytes'})
            payload = json.loads(self.rfile.read(length), strict=False)
            if path == '/api/results':
                result = ingest_results(payload)
            else:
                if not isinstance(payload, dict) or set(payload) != {'token'}:
                    raise ValueError('Expected a token field')
                configure_token(payload['token'])
                result = {'configured': bool(current_token())}
        except (ValueError, TypeError, KeyError, OverflowError):
            return self.send_data(400, {'error': 'Invalid token or results payload; existing data kept'})
        return self.send_data(200, result)

    def do_PATCH(self):
        if urlsplit(self.path).path != '/api/state':
            return self.send_data(404, {'error': 'Not found'})
        # Local operator API: reject cross-origin browser writes. No wildcard CORS.
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            return self.send_data(403, {'error': 'Cross-origin writes are not allowed'})
        if self.headers.get_content_type() != 'application/json':
            return self.send_data(415, {'error': 'Use application/json'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 2_000_000:
                return self.send_data(413, {'error': 'JSON body must be between 1 and 2000000 bytes'})
            patch = json.loads(self.rfile.read(length))
            if not isinstance(patch, dict):
                raise ValueError('Patch must be an object')
            state = update_state(patch)
        except (ValueError, TypeError, OverflowError) as exc:
            return self.send_data(400, {'error': str(exc)})
        return self.send_data(200, state)


if __name__ == '__main__':
    threading.Thread(target=poll_forever, daemon=True).start()
    ThreadingHTTPServer((os.environ.get('APEX_BIND', '127.0.0.1'), int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
