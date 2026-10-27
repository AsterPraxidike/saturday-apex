"""Normalize Respawn private-match results using the uploaded post-game-six schema."""
import json
import re
from datetime import datetime

MAP_NAMES = {'mp_rr_desertlands': "World's Edge", 'mp_rr_tropic_island': 'Storm Point',
             'mp_rr_district': 'E-District', 'mp_rr_olympus': 'Olympus',
             'mp_rr_canyonlands': 'Kings Canyon', 'mp_rr_divided_moon': 'Broken Moon'}


def clean(value):
    return str(value or '').replace('\n', '').replace('\r', '').strip()


def map_name(value):
    name = clean(value)
    for prefix, label in MAP_NAMES.items():
        if name == prefix or name.startswith(prefix + '_'):
            return label
    return name  # Preserve unknown maps rather than guessing.


def number(value):
    result = int(value)
    if isinstance(value, bool) or result != float(value) or result < 0:
        raise ValueError('Results require nonnegative integer placements, kills, and team numbers')
    return result


def cutoff(value):
    if not value:
        return None
    # Explicit offsets are preferred; naive filter dates use the Python server's local time.
    try:
        return datetime.fromisoformat(str(value).strip().replace('Z', '+00:00')).timestamp()
    except ValueError as exc:
        raise ValueError('Invalid results date filter') from exc


def summarize(payload, settings):
    if isinstance(payload, str):
        # Pasted API pages can insert literal line breaks inside string values.
        payload = json.loads(payload, strict=False)
    def repair_keys(value):
        if isinstance(value, dict):
            repaired = {}
            for key, child in value.items():
                key = clean(key)
                if key in repaired:
                    raise ValueError('Duplicate keys after repairing pasted line breaks')
                repaired[key] = repair_keys(child)
            return repaired
        if isinstance(value, list):
            return [repair_keys(child) for child in value]
        return value
    payload = repair_keys(payload)
    if not isinstance(payload, dict) or not isinstance(payload.get('matches'), list):
        raise ValueError('Expected a Respawn object containing a matches list')
    unique = {}
    for match in payload['matches']:
        if not isinstance(match, dict) or not isinstance(match.get('player_results'), list):
            raise ValueError('Every match must contain player_results')
        unique[str(match.get('mid') or match.get('match_start'))] = match
    matches = sorted(unique.values(), key=lambda m: float(m.get('match_start', 0)))
    valid = []
    skipped = 0
    start, end = cutoff(settings.get('countGamesFrom')), cutoff(settings.get('countGamesUntil'))
    for match in matches:
        timestamp = float(match.get('match_start', 0))
        if timestamp > 1e12:
            timestamp /= 1000
        if (start is not None and timestamp < start) or (end is not None and timestamp > end):
            continue
        teams = {}
        for player in match['player_results']:
            if not isinstance(player, dict) or 'teamNum' not in player or 'teamPlacement' not in player or 'kills' not in player:
                raise ValueError('Player results need teamNum, teamPlacement, and kills')
            num = number(player['teamNum'])
            team = teams.setdefault(num, {'name': clean(player.get('teamName')) or f'TEAM {num}',
                                         'num': num, 'placement': 0, 'kills': 0, 'damage': 0, 'players': []})
            placement = number(player['teamPlacement'])
            if team['placement'] and placement and team['placement'] != placement:
                raise ValueError('Conflicting placements for the same team')
            team['placement'] = max(team['placement'], placement)
            team['kills'] += number(player['kills'])
            team['damage'] += number(player.get('damageDealt', 0))
            if player.get('playerName'):
                team['players'].append(clean(player['playerName']))
        # Same abandoned/remade-game rule as the supplied standings screen.
        if not teams or sum(t['placement'] > 0 for t in teams.values()) < max(1, len(teams) / 2):
            skipped += 1
            continue
        valid.append({'timestamp': timestamp, 'match': match, 'teams': list(teams.values())})
    if settings.get('onlyLatestNight', True) and not start and not end and valid:
        newest = valid[-1]['timestamp']
        valid = [m for m in valid if m['timestamp'] >= newest - 8 * 3600]
    skip = set(settings.get('skipGames', []))
    valid = [m for index, m in enumerate(valid, 1) if index not in skip]
    if not valid:
        raise ValueError('No completed games remain after filtering; existing broadcast data kept')
    aliases = settings.get('teams', [])
    by_name = {}
    for game in valid:
        for team in game['teams']:
            alias = next((a for a in aliases if clean(a.get('lobbyName', a.get('name'))).casefold() in
                          (team['name'].casefold(), str(team['num']))), {})
            key = team['name'].casefold()
            aggregate = by_name.setdefault(key, {'name': alias.get('name') or team['name'],
                'lobbyName': team['name'], 'location': alias.get('location', ''), 'adjust': alias.get('adjust', 0), 'games': []})
            aggregate['games'].append([team['placement'], team['kills']])
            team['displayName'] = aggregate['name']
    rankings = []
    pp = settings['placementPoints']
    for team in by_name.values():
        kills = sum(k for _, k in team['games'])
        kill_points = sum(min(k * settings['killPoints'], settings['killCap']) if settings['killCap'] > 0
                          else k * settings['killPoints'] for _, k in team['games'])
        placement_points = sum(pp[p - 1] if 1 <= p <= len(pp) else 0 for p, _ in team['games'])
        placements = [p for p, _ in team['games'] if p > 0]
        rankings.append({'name': team['name'], 'total': kill_points + placement_points + team.get('adjust', 0),
                         'killPoints': kill_points, 'placementPoints': placement_points,
                         'kills': kills, 'wins': sum(p == 1 for p, _ in team['games']),
                         'bestPlacement': min(placements, default=99), 'played': len(team['games'])})
    rankings.sort(key=lambda t: (-t['total'], -t['wins'], -t['kills'], t['bestPlacement'], t['name'].casefold()))
    for i, team in enumerate(rankings):
        previous = rankings[i - 1] if i else None
        tied = previous and all(previous[k] == team[k] for k in ('total', 'wins', 'kills', 'bestPlacement'))
        team['rank'] = previous['rank'] if tied else i + 1
    latest = valid[-1]
    return {'teams': list(by_name.values()), 'rankings': rankings, 'gamesPlayed': len(valid),
            'ignoredAbandoned': skipped, 'mapName': map_name(latest['match'].get('map_name')),
            'latestMatchStart': latest['timestamp'],
            'gameWinners': [t for t in latest['teams'] if t['placement'] == 1]}


def broadcast_patch(summary, total_games):
    leaders = [t['name'] for t in summary['rankings'] if t['rank'] == 1]
    finished = summary['gamesPlayed'] >= total_games > 0
    label = ('SERIES CO-CHAMPIONS' if len(leaders) > 1 else 'SERIES CHAMPION') if finished else 'SERIES LEADER'
    patch = {'global': {}, 'screens': {
        'standings': {'resultsFrom': 'manual', 'teams': summary['teams']},
        'stream-ending': {'champion': ' / '.join(leaders), 'championLabel': label, 'rankings': summary['rankings']}}}
    if summary['mapName']:
        patch['global']['mapName'] = summary['mapName']
    if len(summary['gameWinners']) == 1:
        winner = summary['gameWinners'][0]
        patch['screens']['game-winner'] = {'teamName': winner['displayName'], 'players': winner['players'],
            'kills': winner['kills'], 'damage': f"{winner['damage']:,}",
            'gameNumber': summary['gamesPlayed']}
    return patch
