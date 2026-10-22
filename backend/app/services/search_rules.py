"""Complete, literal EN/ZH grammar for extended local factual searches.

Every clause is consumed before a plan is usable. Names are protected before
country/genre/filler parsing. This is intentionally not semantic search.
"""
from __future__ import annotations

import re
import unicodedata

from pydantic import ValidationError

from app.contracts.search_plan import SearchPlan, SearchPerson
from app.contracts.structured_metadata import normalize_metadata_text
from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY as vocabulary

_EXCLUDE = r"(?:excluding|exclude|except|without|not|不要|排除|不包括|不包含|不是|非)"
_PEOPLE = r"directed by|co-starring|starring|featuring|with|(?<!sorted )(?<!sort )by"
_YEAR = r"(?:(?:18|19|20)\d{2}|2100)"
_STOP = (rf"\s+(?:(?:and\s+)?(?:{_PEOPLE})\b|from\b|released\b|in\b|between\b|"
         rf"under\b|over\b|at least\b|at most\b|shorter\b|longer\b|sorted\b|sort\b|"
         rf"newest\b|oldest\b|{_EXCLUDE}\b)|[,;.!?，。；！？]|$")


def is_extended_request(question: str) -> bool:
    text = normalize_metadata_text(question)
    from app.services.discovery_search import _UNWATCHED
    text = re.sub(_UNWATCHED, " ", text, flags=re.I)
    text = re.sub(r"(?<!\d)\d{4}\s*年代", " ", text)
    return bool(re.search(rf"\b(?:minutes?|hours?|runtime|duration|between|excluding|exclude|except|without|or|co-starring)\b|"
        rf"\bnot\b|不要|排除|不包括|不包含|不是|非日本|或(?:者|是)?|分钟|小时|\b{_YEAR}\b(?!s)|{_YEAR}年", text)
        or len(re.findall(rf"\b(?:{_PEOPLE})\b|执导|导演|主演|出演", text)) > 1
        or re.search(rf"\b(?:{_PEOPLE})\s+.+?\s+and\s+", text))


def parse_extended(question: str):
    try:
        return _parse_extended(question)
    except ValidationError:
        return None, question, "invalid_request"


def grounded_extended(plan: SearchPlan, question: str, *, edited=False) -> bool:
    original, leftover, issue = parse_extended(question)
    return not issue and not leftover and original is not None and (edited or plan == original)


def accepted_interpretation(interpretation, question: str) -> bool:
    """Offline quality gate: schema alone never authorizes a partial model plan."""
    return (interpretation.status == "ready" and interpretation.plan is not None
        and interpretation.confidence >= .9 and not interpretation.unhandled
        and grounded_extended(interpretation.plan, question))


def _parse_extended(question: str):
    # Import lazily to retain the independently tested v1 parser/URL behavior.
    from app.services.discovery_search import (_COUNTRY_WORDS, _FILLERS, _UNWATCHED,
        _WATCHED, _CHINESE_PERSON_PREFIX, _aliases, _replace, _term_pattern, unsupported_reason)
    text = unicodedata.normalize("NFKC", question)
    values: dict = {"version": "search-plan.v2"}
    people = []

    # Full Chinese literal names, including 和/日本/剧情 in a person's name.
    chinese_clause = r"([^,;.!?，。；！？]{1,100}?)(执导|导演|主演|出演)(?:的|(?=[,;.!?，。；！？、\s]|$|电影|影片|作品))"
    explicit = list(re.finditer(r"由\s*" + chinese_clause, text))
    masked = text
    for match in reversed(explicit):
        masked = masked[:match.start()] + " " * (match.end() - match.start()) + masked[match.end():]
    implicit = list(re.finditer(r"(?:^|[,;，。；！？、])\s*" + chinese_clause, masked))
    chinese = sorted(explicit + implicit, key=lambda match: match.start())
    for match in reversed(chinese):
        start = match.start()
        name = match.group(1)
        while prefix := re.match(_CHINESE_PERSON_PREFIX, name):
            name = name[prefix.end():]
        excluded = bool(re.match(rf"^{_EXCLUDE}", name, re.I))
        if excluded:
            name = re.sub(rf"^{_EXCLUDE}\s*", "", name, flags=re.I)
        prefix = re.search(rf"{_EXCLUDE}\s*$", text[:start], re.I)
        if prefix:
            excluded, start = True, prefix.start()
        role = "director" if match.group(2) in ("导演", "执导") else "actor"
        for literal in reversed(name.split("、")):
            people.insert(0, SearchPerson(name=literal.strip(), role=role, exclude=excluded))
        text = text[:start] + " " + text[match.end():]

    # Actor lists share a role. An explicit next role starts another clause.
    if re.search(r"\bwith\s+(?:cinematography|music|screenplay|production|editing)\b", text, re.I):
        return None, text, "unsupported_filter"
    english = list(re.finditer(rf"(?P<neg>{_EXCLUDE}\s+)?\b(?P<role>{_PEOPLE})\s+(?P<names>.+?)(?={_STOP})", text, re.I))
    for match in reversed(english):
        names = match.group("names").strip()
        if re.search(r"\bor\b|或者|或", names, re.I):
            return None, text, "ambiguous_request"
        role = match.group("role").casefold()
        role = "director" if role in ("directed by", "by") else "actor" if role in ("co-starring", "starring", "featuring") else "any"
        parts = re.split(r"\s+and\s+|\s*&\s*|、", names)
        for name in reversed(parts):
            if not name or len(name) > 100:
                return None, text, "ambiguous_request"
            people.insert(0, SearchPerson(name=name.strip(" '’\""), role=role, exclude=bool(match.group("neg"))))
        text = text[:match.start()] + " " + text[match.end():]
    values["people"] = people

    # The guard runs after literal names have been protected; unsupported roles,
    # languages and semantic requirements cannot be reinterpreted as facets.
    guarded = _replace(text, r"\b(?:minutes?|hours?|runtime|duration)\b|分钟|小时")
    guarded = _replace(guarded, rf"{_EXCLUDE}|\bor\b|或者|或是|或|{_YEAR}(?:年)?")
    reason = unsupported_reason(guarded)
    if reason:
        return None, text, reason

    if re.search(_UNWATCHED, text, re.I):
        values["view"] = "unwatched"
        text = _replace(text, _UNWATCHED)
    if re.search(_WATCHED, text, re.I):
        if "view" in values:
            return None, text, "ambiguous_request"
        values["view"] = "watched"
        text = _replace(text, _WATCHED)
    for pattern, sort, direction in (
        (r"\b(?:newest|latest)(?: first)?\b|最新(?:优先)?|年份倒序", "year", "desc"),
        (r"\boldest(?: first)?\b|最早(?:优先)?|年份升序", "year", "asc"),
        (r"\b(?:sort(?:ed)? by )?title\b|按片名", "title", "asc"),
    ):
        if re.search(pattern, text, re.I):
            if "sort" in values:
                return None, text, "ambiguous_request"
            values.update(sort=sort, direction=direction)
            text = _replace(text, pattern)

    # Inclusive ranges are explicit. Strict runtime under/over is represented
    # with integer-minute bounds, so never round an exclusive bound silently.
    ranges = (
        (rf"(?:between|from)\s+({_YEAR})\s+(?:and|to|through|-)\s+({_YEAR})|({_YEAR})\s*(?:年)?\s*(?:至|到|[-–])\s*({_YEAR})(?:年)?", "year"),
        (r"(?:between|from)\s+(\d{1,5})\s+(?:and|to|through|-)\s+(\d{1,5})\s*(?:minutes?|mins?)|(?:片长|时长)?\s*(\d{1,5})\s*(?:至|到|[-–])\s*(\d{1,5})\s*分钟", "duration"),
    )
    for pattern, field in ranges:
        matches = list(re.finditer(pattern, text, re.I))
        if len(matches) > 1:
            return None, text, "ambiguous_request"
        for match in matches:
            lower, upper = [int(part) for part in match.groups() if part is not None]
            values[field + "_min"], values[field + "_max"] = lower, upper
            text = text[:match.start()] + " " + text[match.end():]

    # Runtime inequalities are stored in seconds via exclusive flags below.
    durations = list(re.finditer(r"(?:\b(at least|at most|under|over|shorter than|longer than|less than|more than)\s+(\d{1,5})\s*(minutes?|hours?)\b)|(?:(不少于|不超过|少于|超过|短于|长于)\s*(\d{1,5})\s*(分钟|小时))", text, re.I))
    for match in reversed(durations):
        op, number, unit = [part for part in match.groups() if part is not None]
        op, unit = op.casefold(), unit.casefold()
        value = int(number) * (60 if unit in ("hour", "hours", "小时") else 1)
        lower = op in ("at least", "over", "longer than", "more than", "不少于", "超过", "长于")
        field = "duration_min" if lower else "duration_max"
        if field in values:
            return None, text, "ambiguous_request"
        values[field] = value
        values["duration_min_exclusive" if lower else "duration_max_exclusive"] = op not in ("at least", "at most", "不少于", "不超过")
        text = text[:match.start()] + " " + text[match.end():]

    suffix_durations = list(re.finditer(r"(\d{1,5})\s*(分钟|小时)(以内|以下|以上|不到|以外)", text))
    for match in reversed(suffix_durations):
        value = int(match.group(1)) * (60 if match.group(2) == "小时" else 1)
        lower = match.group(3) in ("以上", "以外")
        field = "duration_min" if lower else "duration_max"
        if field in values:
            return None, text, "ambiguous_request"
        values[field] = value
        values["duration_min_exclusive" if lower else "duration_max_exclusive"] = match.group(3) in ("不到", "以外")
        text = text[:match.start()] + " " + text[match.end():]

    year_bounds = list(re.finditer(rf"\b(before|after|since|through)\s+({_YEAR})\b|({_YEAR})年(之前|以前|之后|以后|起|及以前|及以后)", text, re.I))
    for match in reversed(year_bounds):
        op = (match.group(1) or match.group(4)).casefold()
        value = int(match.group(2) or match.group(3))
        lower = op in ("after", "since", "之后", "以后", "起", "及以后")
        field = "year_min" if lower else "year_max"
        if field in values:
            return None, text, "ambiguous_request"
        values[field] = value + (1 if lower else -1) if op in ("before", "after", "之前", "以前", "之后", "以后") else value
        text = text[:match.start()] + " " + text[match.end():]

    # Exact year and decade become closed year ranges in v2.
    decades = list(re.finditer(rf"(?<!\d)({_YEAR})(?:s\b|\s*年代)", text, re.I))
    for match in reversed(decades):
        value = int(match.group(1))
        if value % 10 or "year_min" in values or value > 2090:
            return None, text, "unsupported_filter"
        values.update(year_min=value, year_max=value + 9)
        text = text[:match.start()] + " " + text[match.end():]
    years = list(re.finditer(rf"(?<!\d)({_YEAR})(?:年)?(?!\d|s)", text, re.I))
    for match in reversed(years):
        if "year_min" in values:
            return None, text, "ambiguous_request"
        values.update(year_min=int(match.group(1)), year_max=int(match.group(1)))
        text = text[:match.start()] + " " + text[match.end():]

    countries = {**vocabulary.country_aliases, **_COUNTRY_WORDS}
    genres = {alias: item.canonical_name for alias, item in vocabulary.genre_aliases.items()}
    negatives = {"countries": [], "genres": []}
    negative_clauses = list(re.finditer(rf"{_EXCLUDE}\s*([^,;.!?，。；！？]+)", text, re.I))
    for match in reversed(negative_clauses):
        tail, found_countries = _aliases(match.group(1), countries)
        tail, found_genres = _aliases(tail, genres)
        if bool(found_countries) == bool(found_genres):
            return None, text, "negation"
        found = found_countries or found_genres
        field = "countries" if found_countries else "genres"
        spans = sorted(re.search(_term_pattern(term), match.group(1), re.I).span() for term in found.values())
        if any(not re.fullmatch(r"\s*(?:or|或者|或是|或)\s*", match.group(1)[left[1]:right[0]], re.I)
               for left, right in zip(spans, spans[1:])):
            return None, text, "ambiguous_request"
        tail = _replace(tail, r"\bor\b|或者|或是|或")
        if re.sub(r"[\s'’\"]", "", _replace(tail, _FILLERS)):
            return None, text, "incomplete_request"
        negatives[field].extend(found)
        text = text[:match.start()] + " " + text[match.end():]
    # Only explicit local facet alternatives and exclusions are recognized.
    # Unknown negative values remain unconsumed, never interpreted as absence.
    for aliases, field in ((countries, "countries"), (genres, "genres")):
        before = text
        text, found = _aliases(text, aliases)
        if len(found) > 1:
            spans = sorted(re.search(_term_pattern(term), before, re.I).span() for term in found.values())
            if any(not re.fullmatch(r"\s*(?:or|或者|或是|或)\s*", before[left[1]:right[0]], re.I)
                   for left, right in zip(spans, spans[1:])):
                return None, text, "ambiguous_request"
        values[field] = sorted(found)
        values["exclude_" + field] = sorted(set(negatives[field]))
    # OR is legal only between values within one facet dimension, not between
    # whole conditions such as 'Japanese or under 90 minutes'.
    or_count = len(re.findall(r"\bor\b|或者|或是|或", text, re.I))
    allowed_or = sum(max(0, len(values.get(field, [])) - 1) for field in ("countries", "genres"))
    if or_count > allowed_or:
        return None, text, "ambiguous_request"
    text = _replace(text, r"\bor\b|或者|或是|或")
    leftover = re.sub(r"[\s.,!?，。！？、:：;；\-–—'’\"]", "", _replace(text, _FILLERS))
    try:
        return SearchPlan(**values), leftover, None
    except ValidationError:
        return None, text, "invalid_request"
