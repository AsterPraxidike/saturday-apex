"""Calendar weeks counted from an explicit season-opening Saturday."""
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def broadcast_schedule(shared, now=None):
    start = shared.get('seasonStart')
    timezone = shared.get('broadcastTimezone', 'America/Chicago')
    if not isinstance(timezone, str):
        raise ValueError('Broadcast timezone must be an IANA timezone name')
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError('Unknown broadcast timezone; use e.g. America/Chicago') from exc
    if not start:
        return {'automatic': False, 'week': shared.get('week'), 'timezone': timezone}
    if not isinstance(start, str):
        raise ValueError('Week 1 Saturday must be a date in YYYY-MM-DD format')
    try:
        anchor = date.fromisoformat(start)
    except ValueError as exc:
        raise ValueError('Week 1 Saturday must be a date in YYYY-MM-DD format') from exc
    if anchor.weekday() != 5:
        raise ValueError('Week 1 date must be a Saturday')
    if not isinstance(shared.get('season'), str) or not shared['season'].strip():
        raise ValueError('Set a season label with the Week 1 Saturday')
    if now is None:
        today = datetime.now(zone).date()
    else:
        if now.tzinfo is None:
            raise ValueError('Current time must include a timezone')
        today = now.astimezone(zone).date()
    week = max(0, (today - anchor).days // 7 + 1)
    return {'automatic': True, 'week': week, 'timezone': timezone, 'seasonStart': start,
            'today': today.isoformat()}
