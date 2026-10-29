"""Bounded literal requests backed by exact local identities, never fuzzy titles.

Only a complete wrapper/qualifier can be consumed. Check a real punctuation-
bearing title before considering a sentence terminator. No catalog or identity
list is sent to a model; unknown residual clauses cannot authorize partial SQL.
"""
from dataclasses import dataclass
import re
import unicodedata
from pydantic import ValidationError

from app.contracts.bound_search_plan import SearchPlan
from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY as vocabulary

_LEAD = re.compile(r"^(?:(?:please\s+)?(?:find|show me|look for|i want to (?:find|watch)|i would like to (?:find|watch))\s+|"
                   r"(?:请帮我找|请帮我寻找|帮我找|请找|我想找|我要找|我想看|我要看|只找|只要|必须是|有没有)\s*)", re.I)
_QUOTE = re.compile(r'''^(?:《([^》]+)》|“([^”]+)”|"([^"]+)"|'([^']+)')''')
_ONLY = re.compile(r"^(?:(?:exact (?:film|movie) only|(?:the )?(?:film|movie) only|only|no substitutes|"
                   r"no similar (?:films|movies|recommendations)|不(?:要|用)相似推荐|只要(?:这部|这一部)|这部电影|这部影片|这部片|这部|的电影)"
                   r"[\s,;.!?，。；！？]*)+$", re.I)
_NEGATIVE = re.compile(r"\b(?:but not|do not recommend|excluding|exclude|except|not)\s+|(?:但)?(?:排除|不要|不包括|不包含)\s*", re.I)
_EXACT_ONLY = re.compile(r"\b(?:only|no substitutes|no similar)\b|不(?:要|用)相似推荐|只要(?:这部|这一部)", re.I)


@dataclass(frozen=True)
class LiteralBinding:
    keyword: str | None = None
    plan: SearchPlan | None = None
    issue: str | None = None


def terminal_variants(text):
    value = text.strip()
    yield value
    # A single sentence period is considered only after the full literal.
    if value.endswith((".", "。")):
        yield value[:-1].rstrip()


def normalize_negative_years(text):
    year = r"((?:18|19|20)\d{2}|2100)"
    text = re.sub(rf"\b(?:not|excluding)\s+(?:(?:anything|films?|movies?)\s+)?(?:released\s+)?(?:from\s+)?(before|after)\s+{year}",
                  lambda m: ("since " if m[1].lower() == "before" else "through ") + m[2], text, flags=re.I)
    return re.sub(rf"(?:不要|排除|不包括)\s*{year}年(?:以|之)(前|后)(?:的)?(?:电影|影片)?",
                  lambda m: m[1] + ("年起" if m[2] == "前" else "年及以前"), text)


def _prefix_title(text, lookup):
    quoted = _QUOTE.match(text)
    if quoted:
        title = next(v for v in quoted.groups() if v is not None)
        return title, lookup(title), quoted.end(), True
    prefix = re.match(r"(?:the\s+)?(?:film|movie)\s+", text, re.I)
    start = prefix.end() if prefix else 0
    tail = text[start:]
    ends = {len(tail)}
    ends.update(m.start() for m in re.finditer(r"[,;，；]|\s+(?:and|or|but|before|after|since|through|released)\b", tail, re.I))
    for end in sorted(ends, reverse=True)[:24]:
        for title in terminal_variants(tail[:end]):
            if not title or len(title) > 200:
                continue
            rows = lookup(title)
            # An unqualified facet word remains a facet, not a coincidental Film.
            if rows and (prefix or not (vocabulary.resolve_country(title) or vocabulary.resolve_genre(title))):
                return title, rows, start + end, False
    return None


def title_exclusions(text, lookup):
    """Consume only proven title clauses. Leave roles/facets to the v2 parser."""
    excluded, cursor = [], 0
    for _ in range(8):
        match = _NEGATIVE.search(text, cursor)
        if match is None:
            break
        start = match.end()
        original = re.match(r"(?:the\s+)?original\s+", text[start:], re.I)
        if original:
            start += original.end()
        if re.match(r"(?:directed by|starring|by|produced by|written by)\b|(?:由).+(?:执导|主演)|.+(?:导演|执导|主演)(?:的|$)", text[start:], re.I):
            cursor = match.end()
            continue
        found = _prefix_title(text[start:], lookup)
        if not found:
            cursor = match.end()
            continue
        title, rows, end, quoted = found
        if not rows:
            return text, [], "unknown_film"
        if len(rows) != 1:
            return text, [], "ambiguous_film"
        excluded.append(rows[0]["key"])
        finish = start + end
        while join := re.match(r"\s+(?:or|and)\s+|\s*(?:或|以及|和)\s*", text[finish:], re.I):
            next_start = finish + join.end()
            following = _prefix_title(text[next_start:], lookup)
            if not following:
                break
            _, choices, size, _ = following
            if len(choices) != 1:
                return text, [], "ambiguous_film" if choices else "unknown_film"
            excluded.append(choices[0]["key"])
            finish = next_start + size
        if len(excluded) > 8:
            return text, [], "incomplete_request"
        text = text[:match.start()] + " " + text[finish:]
        cursor = match.start() + 1
    return text, sorted(set(excluded)), None


def hard_plan(text, lookup=None, *, allow_languages=False):
    from app.services.search_rules import parse_extended
    value = normalize_negative_years(text).strip(" ,;，；")
    excluded = []
    if lookup:
        # Check complete literal punctuation before grammar removes sentence
        # terminators, metadata words or filler inside a title.
        value, excluded, issue = title_exclusions(value, lookup)
        if issue:
            return None, issue
    value = value.strip(" ,;，；。.!?")
    if not allow_languages and re.search(r"\b(?:audio|languages?|dubbed|dubbing)\b|\b(?:French|Japanese|English|Korean|Chinese|German|Italian|Spanish|Hindi|Arabic|Russian|Portuguese|Cantonese|Mandarin)[- ](?:language|speaking)\b|"
                 r"\bin\s+(?:French|Japanese|English|Korean|Chinese|German|Italian|Spanish|Hindi|Arabic|Russian|Portuguese|Cantonese|Mandarin)\b|"
                 r"日语|法语|英语|韩语|中文|汉语|国语|德语|意大利语|西班牙语|粤语|配音", value, re.I):
        return None, "unsupported_filter"
    if re.search(r"\b(?:with|having)\s+(?:a\s+)?(?:rating|score)\b|\b(?:rated|favorites?|notes?|subtitles?|resolution|IMDb|TMDB|Douban)\b|"
                 r"评分|星级|收藏|笔记|字幕|分辨率", value, re.I):
        return None, "unsupported_filter"
    if re.search(r"\b(?:produced|written|composed|edited)\s+by\b|\bby\s+(?:producers?|writers?|screenwriters?|composers?|editors?)\b|"
                 r"\bwith\s+(?:cinematography|music|screenplay|production|editing)\b|制片|监制|编剧|出品|摄影|配乐|作曲|剪辑", value, re.I):
        return None, "unsupported_filter"
    # Clause connectors at a boundary, never characters inside a literal name.
    value = re.sub(r"^(?:and|but)\s+|^(?:但是|但)(?=排除|不要|由|\d)", "", value, flags=re.I)
    plan, leftover, issue = parse_extended(value or "films")
    if issue or leftover or plan is None:
        return None, issue or "incomplete_request"
    try:
        return SearchPlan.model_validate({**plan.model_dump(), "exclude_film_ids": excluded}), None
    except ValidationError:
        return None, "invalid_request"


def bind_literal(question, lookup, known_person=lambda text: False):
    text = unicodedata.normalize("NFKC", question).strip()
    # The complete literal always wins over wrapper-looking title words.
    if lookup(text) or known_person(text):
        return LiteralBinding(keyword=text)
    lead = _LEAD.match(text)
    body = text[lead.end():] if lead else text
    leading_only = bool(lead and re.match(r"只找|只要", lead[0]))

    def literal(title, tail=""):
        if not leading_only and not _EXACT_ONLY.search(tail):
            return LiteralBinding(keyword=title)
        choices = lookup(title)
        if not choices:
            return LiteralBinding(issue="unknown_film")
        if len(choices) != 1:
            return LiteralBinding(issue="ambiguous_film")
        return LiteralBinding(plan=SearchPlan(version="search-plan.v2", film_ids=[choices[0]["key"]]))

    if lead:
        body = re.sub(r"^(?:the\s+)?(?:film|movie)\s+", "", body, flags=re.I)
    quote = _QUOTE.match(body)
    if quote:
        title = next(v for v in quote.groups() if v is not None).strip()
        if len(title) > 200:
            return LiteralBinding(issue="long_keywords")
        tail = body[quote.end():].strip(" ,;，；。.!?！？")
        if not tail or _ONLY.fullmatch(tail):
            return literal(title, tail)
        choices = lookup(title)
    else:
        for term in terminal_variants(body):
            if lookup(term) or known_person(term):
                return literal(term)
        # No arbitrary truncation: a known full prefix and a complete qualifier
        # are both required, or an explicit exact-only phrase for an absent title.
        choices, title, tail = [], None, None
        exact_only_keyword = None
        ends = [m.start() for m in re.finditer(r"[,;，；]|\s+(?=directed by\b|starring\b|released\b|before\s+\d|after\s+\d)", body, re.I)]
        for end in reversed(ends[:24]):
            left, right = body[:end].strip(), body[end:].strip(" ,;，；。.!?")
            if _ONLY.fullmatch(right) and left and len(left) <= 200:
                if lookup(left):
                    return literal(left, right)
                exact_only_keyword = (left, right)
                continue
            rows = lookup(left)
            if rows:
                choices, title, tail = rows, left, right
                break
        if title is None:
            return literal(*exact_only_keyword) if exact_only_keyword else None
    if not choices:
        return LiteralBinding(issue="unknown_film")
    if len(choices) > 8:
        return LiteralBinding(issue="ambiguous_film")
    plan, issue = hard_plan(tail, lookup)
    if issue:
        # A credited-name qualifier is accepted as any actor/director role,
        # never guessed to be a director, producer or writer.
        qualifier = re.fullmatch(r"(?:the\s+)?(.{1,100}?)\s+(?:film|movie)\s+(?:from|released in)\s+((?:18|19|20)\d{2}|2100)", tail, re.I)
        if qualifier:
            from app.contracts.search_plan import SearchPerson
            plan = SearchPlan(version="search-plan.v2", people=[SearchPerson(name=qualifier[1], role="any")],
                              year_min=int(qualifier[2]), year_max=int(qualifier[2]))
        else:
            return LiteralBinding(issue=issue)
    try:
        return LiteralBinding(plan=SearchPlan.model_validate({**plan.model_dump(), "film_ids": sorted({r["key"] for r in choices})}))
    except ValidationError:
        return LiteralBinding(issue="invalid_request")
