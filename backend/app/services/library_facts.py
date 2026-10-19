"""Effective Library scalar facts shared by deterministic filters and Ask."""
from sqlalchemy import case, func


def effective_duration_sql(payload):
    seconds = payload["primary_item"]["video"]["duration_seconds"].as_float()
    minutes = payload["runtime_minutes"].as_integer()
    return func.coalesce(case((seconds > 0, seconds)), case((minutes > 0, minutes * 60)))


def duration_fact(film):
    seconds = ((film.get("primary_item") or {}).get("video") or {}).get("duration_seconds")
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds > 0:
        return {"field": "duration", "value": seconds, "unit": "seconds", "source": "video"}
    minutes = film.get("runtime_minutes")
    if isinstance(minutes, (int, float)) and not isinstance(minutes, bool) and minutes > 0:
        return {"field": "duration", "value": minutes * 60, "unit": "seconds", "source": "film_runtime"}
    return None


def rating_fact(film):
    value = (film.get("profile_state") or {}).get("rating")
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 5:
        return {"field": "rating", "value": value, "unit": "stars", "source": "film_profile"}
    return None
