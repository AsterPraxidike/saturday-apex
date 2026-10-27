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
    skips = shared.get('skippedSaturdays', [])
    if not isinstance(skips, list) or any(not isinstance(day, str) for day in skips):
        raise ValueError('Skipped Saturdays must be a list of YYYY-MM-DD dates')
    try:
        skipped = [date.fromisoformat(day) for day in skips]
    except ValueError as exc:
        raise ValueError('Skipped Saturdays must use YYYY-MM-DD dates') from exc
    if len(set(skipped)) != len(skipped) or any(day.weekday() != 5 for day in skipped):
        raise ValueError('Skipped dates must be distinct Saturdays')
    if not start:
        return {'automatic': False, 'week': shared.get('week'), 'timezone': timezone}
    if not isinstance(start, str):
        raise ValueError('Week 1 Saturday must be a date in YYYY-MM-DD format')
    try:
        anchor = date.fromisoformat(start)
    except ValueError as exc:
        raise ValueError('Week 1 Saturday must be a date in YYYY-MM-DD format') from exc
    if any(day <= anchor for day in skipped):
        raise ValueError('Skipped Saturdays must be after Week 1 Saturday')
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
    week = max(0, (today - anchor).days // 7 + 1 - sum(day <= today for day in skipped))
    return {'automatic': True, 'week': week, 'timezone': timezone, 'seasonStart': start,
            'today': today.isoformat(), 'skippedSaturdays': sorted(skips), 'skippedToday': today in skipped}
