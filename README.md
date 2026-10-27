# Apex live broadcast screens

Python owns the broadcast settings. OBS pages poll their effective settings every 500 ms and redraw automatically when those settings change. You do not need to refresh the OBS Browser Source. All settings formerly in each HTML `SETTINGS` block are now in `defaults.json`, served from Python state.

This includes the latest uploaded standings and intermission revisions. Original uploaded files remain separately under `/workspace/apex-reference` in the onboarding environment.

## Run

```bash
cd /workspace/saturday-apex
mkdir -p /workspace/.docker
DOCKER_CONFIG=/workspace/.docker docker compose up -d --build
```

The intended public host is **apex.praxidike.space**. Use these OBS Browser Source URLs at 1920 × 1080 once it is deployed:

- `https://apex.praxidike.space/starting-soon`
- `https://apex.praxidike.space/intermission`
- `https://apex.praxidike.space/standings`
- `https://apex.praxidike.space/ingame-overlay`
- `https://apex.praxidike.space/game-winner`
- `https://apex.praxidike.space/stream-ending`

The operator page is `https://apex.praxidike.space/control`. `APEX_PUBLIC_URL` configures the advertised URLs and defaults to this host. The clean page paths work locally too, and existing `.html` paths remain compatible. Page assets and live requests use relative paths on the host serving the page.

DNS, HTTPS, and deployment to your separate machine have not been performed. On that machine, route this hostname through your reverse proxy to the Docker app on local port 8080, preserving the incoming Host header. Forward the screen, render, API, and asset paths together. Keep operator paths (`/`, `/control`, `/api/state`, POST `/api/results`, and `/api/respawn/token`) behind your private access/authentication; OBS needs public GET access to the screen paths, `/render/*`, `/api/screens/*`, and assets. The app's local operator API does not itself implement authentication. Docker stays bound to loopback for use behind that proxy. This cloud task's loopback address is not reachable from your OBS machine.

In the control page, use the Season/Week fields, weekly token box, and production-staff role/name editor. Choose Shared settings or a screen to edit text fields, switches, numbers, colors, and expandable lists, then select Save fields live. Production staff are edited as roles with one name per line and saved with Save production staff; their names populate the ending credits. An Advanced JSON editor remains available when needed. Shared settings override matching setting names on every screen that supports them. For example, `colors` affects all six screens; `season` affects screens that display a season. Screen-specific values stay separate unless overridden. Lists replace the entire list. Remove a shared override using its Remove button (or delete the key in Advanced JSON) (or send null through the API) to restore the screen-specific values. Apply accepts patches; to remove an individual nested shared color, clear the shared `colors` key and reapply the colors you want.

Edits are saved atomically to a named Docker volume and survive container restarts and rebuilds. Do not use `docker compose down -v` unless you intend to delete saved settings. `defaults.json` seeds a fresh state; edit the running state through the API/control page after first startup.

## Weekly broadcast details

The control page has Season, Week, and Stage fields. Update them once for the broadcast: Starting Soon, Intermission, Standings, Game Winner, the in-game badge, and Stream Ending's side label follow the same season/week. Week changes are operator-controlled; no calendar schedule has been supplied.

```python
from controller import set_broadcast, set_globals
set_broadcast(season="SPRING 2027", week=2)
set_globals(mapName="Olympus", gameNumber=3)
```

When shared `week` is present, the app generates `eventLine` and `sideText` from the shared season, week, and stage. The in-game badge reads `SPRING 2027 WEEK 2 // Olympus`. These generated labels take precedence over literal eventLine/sideText settings; clear shared `week` to return to literal labels. Season must be supplied with week. Map updates also reach Game Winner.

The Respawn private-match endpoint is fetched by Python. Enter this week's token in the dedicated token field, or call `set_stats_token(token)` from Python. Tokens are saved in operator state in the Docker volume, not in code defaults. Changing the token clears last week's standings, champion, latest map, and game winner while preserving school aliases and adjustments. Use the dedicated token button/helper rather than editing the token list directly, so this cleanup happens. Polling runs every 30 seconds by default; a new token may take up to one interval to be queried. Disable API polling with the dedicated button when using imported snapshots only.

The control page also imports Respawn JSON/text files, including the supplied post-game-six sample with line wraps inside JSON strings/keys. Both fetched and imported results use the same Python parser and scoring. Match records are de-duplicated and sorted by time; abandoned games are excluded using the supplied standings rule (at least half the teams have placements). The latest-night/date/skip-game settings remain available. Placement points, kill points/caps, adjustments, and ties use the original standings rules: total points, wins, kills, then best placement. Exact ties remain tied.

Python updates standings, Game Winner, and Stream Ending's champion and ranked credits together. A series leader is labeled as such until the configured number of games has completed. At that point the ending label becomes Series Champion (or Co-Champions for an unresolved tie). School names come from the API's teamName; use standings team entries with name/lobbyName aliases for official school display names. Changing aliases/scoring affects the next API poll or import.

The API provides the latest **completed** game's map and results. It does not establish the next game's map or that a match is currently running. You can set mapName manually between games, and an unchanged API response leaves that manual value alone. New or changed results restore the last completed map. Date filters with no timezone use the Python server’s local timezone; include an offset for unambiguous filtering. Current/next-map scheduling and a broader ending-screen redesign remain future work.

Live cloud requests are currently blocked by the egress proxy (CONNECT 403). The required domain `r5-crossplay.r5prod.stryder.respawn.com` has been saved in the environment's draft network settings; review/save those settings to apply access, then publish the environment. Polling retries automatically. Imported results work without Respawn network access. A failed fetch preserves the last good scores and is shown in the control page's API status.

## Control from Python

From this checkout, with the server running:

```python
from controller import set_globals, set_screen, set_stats_token, import_results

# Tokens change weekly. Supply the token from your own local input/configuration.
# set_stats_token(weekly_token)
# import_results(Path("results.json").read_text())  # from pathlib import Path
set_globals(eventLine="COLLEGIATE FINALS", colors={"red": "#bd180a"})
set_screen("intermission", showTrivia=True)
set_screen("ingame-overlay", gameNumber=3, mapName="World's Edge", showPause=False)
set_screen("standings", resultsFrom="manual", teams=[
    {"name": "TEAM ONE", "games": [[1, 7], [12, 2]]},
    {"name": "TEAM TWO", "games": [[2, 4], [1, 5]]},
])
```

`GET /api/state` reads all state; `PATCH /api/state` accepts `{"global": {...}, "screens": {"intermission": {...}}}`. Arrays replace arrays; objects merge recursively. `GET /api/screens/intermission` returns effective settings. `GET /api/health` checks readiness. The local operator API has no login and should stay local.

For native Python development, no external runtime dependencies are required:

```bash
python3 app.py
```

Native state is saved in ignored `data/state.json`. `APEX_STATE_FILE`, `APEX_BIND`, and `PORT` can override the path, bind address, and port.

## Update behavior and limits

An affected screen is rendered again inside its live wrapper: entrance animations, trivia rotation, and other animations restart on edits. Saved duration countdown targets persist through redraws. Clock-based countdowns and URL timer overrides retain the original screen behavior. Unchanged screens are not redrawn. This is automatic redraw, not frame-by-frame mutation of every DOM element.

Python now fetches and calculates the Respawn results and sends manual team-game inputs to the original standings renderer. OBS does not fetch Respawn directly. The server has been tested using the uploaded data and mocked polling; a successful live Respawn request remains unverified because cloud egress is blocked. Direct manual team games and pasted data remain supported, but active API polling can replace manual edits on its next successful sync.

Bundled offline font fallbacks remain available. Google Fonts is optional. OBS integration on the streaming machine is still to be checked.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

The 16 tests cover shared precedence, weekly metadata, screen isolation, persistence, rejected updates, override removal, list replacement, the real post-game-six scores, abandoned records, deduplication, school aliases, map IDs, tied champions, weekly token cleanup, and failed-poll data retention. Browser checks rendered all six pages and exercised Python updates, control-page edits, and imported API results. The fixture retains team scores and omits player identifiers.

Intermission no longer displays an Up Next band; the results feed only describes completed games.

Operator GUI validation (isolated server and temporary state; requires Playwright and Chromium): `python3 tests/gui_smoke.py`. This checks week, token entry, production roles/names, text fields, switches, lists, and saved values after reload.
