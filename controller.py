"""Call set_globals / set_screen from your Python automation while the server runs."""
import json
from urllib.request import Request, urlopen


def patch_state(patch, base_url='http://127.0.0.1:8080'):
    request = Request(base_url + '/api/state', data=json.dumps(patch).encode(),
                      headers={'Content-Type': 'application/json'}, method='PATCH')
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def set_globals(base_url='http://127.0.0.1:8080', **settings):
    return patch_state({'global': settings}, base_url)


def set_screen(screen, base_url='http://127.0.0.1:8080', **settings):
    return patch_state({'screens': {screen: settings}}, base_url)


def set_broadcast(season, week, phase='REGULAR SEASON', base_url='http://127.0.0.1:8080'):
    """Change every broadcast season/week label in one persistent update."""
    return set_globals(base_url=base_url, season=season, week=week, phase=phase)


def post(path, payload, base_url='http://127.0.0.1:8080'):
    request = Request(base_url + path, data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def set_stats_token(token, base_url='http://127.0.0.1:8080'):
    """Change the weekly token and clear previous-week scores; empty disables API polling."""
    return post('/api/respawn/token', {'token': token}, base_url)


def import_results(payload, base_url='http://127.0.0.1:8080'):
    """Import the same matches JSON supplied by the Respawn private-match API."""
    if isinstance(payload, str):
        payload = json.loads(payload, strict=False)
    return post('/api/results', payload, base_url)
