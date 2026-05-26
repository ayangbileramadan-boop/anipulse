import datetime

from django.utils import timezone


def surrogatefree(value):
    """Strip lone surrogate characters (U+D800-U+DFFF) from a string."""
    if value is None:
        return ''
    return ''.join(c for c in str(value) if ord(c) not in range(0xD800, 0xE000))


def parse_anilist_date(date_dict: dict) -> datetime.date | None:
    """Parse AniList {year, month, day} dict into a Python date."""
    if not date_dict:
        return None
    y, m, d = date_dict.get('year'), date_dict.get('month'), date_dict.get('day')
    if y and m and d:
        try:
            return datetime.date(y, m, d)
        except ValueError:
            return None
    return None


def unix_to_datetime(ts: int | None) -> datetime.datetime | None:
    """Convert a Unix timestamp to an aware datetime."""
    if ts is None:
        return None
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)


def get_current_season() -> tuple[str, int]:
    """Return the current anime season name and year."""
    now = timezone.now()
    month = now.month
    year = now.year
    if month in (1, 2, 3):
        season = 'WINTER'
    elif month in (4, 5, 6):
        season = 'SPRING'
    elif month in (7, 8, 9):
        season = 'SUMMER'
    else:
        season = 'FALL'
    return season, year
