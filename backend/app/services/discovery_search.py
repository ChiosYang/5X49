"""Conservative local routing in front of the existing factual Ask interpreter.

No catalog or personal state is supplied to a provider. Rules must consume the
whole request, and an AI plan must be grounded in the original, not just valid JSON.
"""
from __future__ import annotations

import re
from sqlmodel import Session, select

from app.contracts.ask import AskPlan, AskQueryRequest, AskResolveRequest
from app.contracts.discovery_search import DiscoveryQuestion, DiscoveryQuery
from app.contracts.bound_search_plan import SearchPlan
from app.canonical_models import FilmSearchReadModel, LibraryFilmReadModel
from app.contracts.structured_metadata import normalize_metadata_text
from app.services import ask as ask_module
from app.services.ask import AskError, ask_service, has_private_input
from app.services.search_execution import search_plan_executor
from app.services.search_rules import is_extended_request, parse_extended, grounded_extended
from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY as vocabulary


_COUNTRY_WORDS = {"japanese": "JP", "french": "FR", "american": "US", "chinese": "CN",
                  "british": "GB", "korean": "KR", "german": "DE", "italian": "IT",
                  "spanish": "ES", "indian": "IN", "canadian": "CA"}
_UNWATCHED = r"\bunwatched\b|\bunseen\b|\bnot (?:yet )?(?:watched|seen)\b|\bhaven['’]t (?:watched|seen)(?: yet)?\b|未看(?:过)?|没看(?:过)?|尚未看(?:过)?"
_WATCHED = r"\bwatched\b|\bseen\b|已看(?:过)?|看过"
_REQUEST = r"\b(?:find|show|want|looking|movies?|films?|cinema|unwatched|watched|directed|starring|recommend|similar|something|shorter|longer)\b|找|想看|电影|影片|未看|已看|导演|执导|主演|推荐|相似|类似|治愈|烧脑"
_FILLERS = (r"\b(?:please|find|show|me|us|i|have|want|would|like|to|watch|see|looking|for|"
            r"movies?|films?|cinema|features?|that|which|are|were|was|is|the|a|an|some|all|only|"
            r"local|library|collection|from|in|of|during|released|made|and|my|featuring)\b|\bproduced in\b|"
            r"我想看|我想找|想看|想找|找一些|给我|请|找|有哪些|有没有|片库里|库里|片库|本地|"
            r"电影|影片|片子|作品|一部|一些|全部|所有|上映|发行|来自|以及|的|和")
_LANGUAGES = r"French|Japanese|English|Korean|Chinese|German|Italian|Spanish|Hindi|Arabic|Russian|Portuguese|Cantonese|Mandarin"
_CHINESE_PERSON_PREFIX = (r"^(?:(?:我想看|我想找|想看|想找|请给我|给我|找一些|请|找|有哪些|有没有)|"
                          r"(?:未看(?:过)?|没看(?:过)?|已看(?:过)?)(?:的)?)\s*")


def _replace(text, pattern, value=" "):
    return re.sub(pattern, value, text, flags=re.IGNORECASE)


def keyword_text(question):
    # Only an explicit leading search command is removed. Never strip title
    # words such as The/In or occurrences of 找/find inside the title.
    match = (re.match(r"^(?:please\s+)?find\s+(.+)$", question, re.IGNORECASE)
             or re.match(r"^(?:请)?(?:帮我)?找(?:一下)?\s*(.+)$", question))
    return match.group(1).strip() if match else question


def _term_pattern(term):
    escaped = re.escape(term)
    return (r"(?<!\w)" + escaped + r"(?!\w)") if term.isascii() else escaped


def _aliases(text, aliases):
    found = {}
    for term, value in sorted(aliases.items(), key=lambda item: -len(item[0])):
        # Lowercase two-letter ISO codes such as 'in' and 'us' are ordinary words.
        if len(term) == 2 and term.isascii():
            pattern = r"(?<!\w)" + re.escape(term.upper()) + r"(?!\w)"
            if re.search(pattern, text):
                found[value] = value
                text = re.sub(pattern, " ", text)
        elif re.search(_term_pattern(term), text, re.IGNORECASE):
            found[value] = term
            text = _replace(text, _term_pattern(term))
    return text, found


def unsupported_reason(text):
    """Legacy v1 guard; v2 local grammar validates its own complete requirements."""
    text = _replace(text, _UNWATCHED)
    rules = (
        ("non_search", r"\b(?:sql|delete|scrape|write|download|rename|password|api.key)\b|删除|下载|修改|重命名|刮削|私人笔记|私密笔记"),
        ("similarity", r"\b(?:similar|similarity|style|theme|mood|plot|story|about|uplifting|comforting|feel.good)\b|相似|类似|风格|主题|剧情讲|关于|治愈|温暖|烧脑|心情"),
        ("recommendation", r"\b(?:recommend|taste|preferences|best|classics?)\b|推荐|口味|偏好|最好|经典"),
        ("negation", r"\b(?:exclude|excluding|except|without|not|isn['’]t)\b|不要|排除|不包含|不包括|不是|非日本"),
        ("multiple_values", r"\bor\b|或者|或是|合作|共同出演|共同主演|co.starring"),
        ("unsupported_filter", r"\b(?:produced|producing)\b(?!\s+in\b)|\b(?:producers?|written|writers?|screenwriters?|screenplay|cinematography|cinematographers?|composed|composers?|edited|editors?)\b|制片|监制|编剧|出品|摄影|配乐|作曲|剪辑"),
        ("unsupported_filter", rf"\bin\s+(?:{_LANGUAGES})\b|\b(?:{_LANGUAGES})[- ](?:language|speaking)\b|\b(?:languages?|dubbed|dubbing|audio)\b|日语|法语|英语|韩语|中文|汉语|国语|德语|意大利语|西班牙语|粤语|配音"),
        ("unsupported_filter", r"\b(?:IMDb|TMDB|Douban|rating|rated|stars?|minutes?|hours?|runtime|duration|favorites?|notes?|subtitles?|resolution)\b|豆瓣|评分|星级|时长|分钟|小时|收藏|笔记|字幕|分辨率"),
    )
    for reason, pattern in rules:
        if re.search(pattern, text, re.IGNORECASE):
            return reason
    if re.search(r"(?<!\d)(?:18|19|20|21)\d{2}(?!\d|s|\s*年代)", text, re.IGNORECASE):
        return "unsupported_filter"
    return None


def _chinese_person(text):
    # Explicit 由 is the name boundary even when other filters precede it.
    # Without it, remove only an anchored request prefix, never filler/facet
    # words inside the literal name (是枝裕和, 和田诚, 日本太郎, 喜剧人...).
    explicit = list(re.finditer(r"由\s*([^，。！？]{1,100}?)(执导|导演|主演|出演)(?:的)?", text))
    masked = text
    for match in reversed(explicit):
        masked = masked[:match.start()] + " " * (match.end() - match.start()) + masked[match.end():]
    implicit = list(re.finditer(r"(?:^|[，。！？])\s*([^，。！？]{1,100}?)(执导|导演|主演|出演)(?:的)?", masked))
    if len(explicit) + len(implicit) > 1:
        return text, {}, "multiple_values"
    if not explicit and not implicit:
        return text, {}, None
    match = (explicit or implicit)[0]
    start, name = match.start(), match.group(1)
    if not explicit:
        start = match.start(1)
        while prefix := re.match(_CHINESE_PERSON_PREFIX, name):
            start += prefix.end()
            name = name[prefix.end():]
    name = name.strip()
    if not name:
        return text, {}, "ambiguous_request"
    role = "director" if match.group(2) in ("执导", "导演") else "actor"
    return text[:start] + " " + text[match.end():], {"person": name, "person_role": role}, None


def local_plan(question):
    """Return exact fields plus unconsumed text; never silently discard it."""
    text, values, issue = _chinese_person(question)
    if issue:
        return values, text, issue
    if re.search(_UNWATCHED, text, re.IGNORECASE):
        values["view"] = "unwatched"
        text = _replace(text, _UNWATCHED)
    if re.search(_WATCHED, text, re.IGNORECASE):
        if "view" in values:
            return values, text, "multiple_values"
        values["view"] = "watched"
        text = _replace(text, _WATCHED)
    for pattern, sort, direction in (
        (r"\b(?:newest|latest)(?: first)?\b|最新(?:优先)?|年份倒序", "year", "desc"),
        (r"\boldest(?: first)?\b|最早(?:优先)?|年份升序", "year", "asc"),
        (r"\b(?:sort(?:ed)? by )?title\b|按片名", "title", "asc"),
    ):
        if re.search(pattern, text, re.IGNORECASE):
            if "sort" in values:
                return values, text, "multiple_values"
            values.update(sort=sort, direction=direction)
            text = _replace(text, pattern)
    raw_decades = set(re.findall(r"(?<!\d)(\d{4})(?:s\b|\s*年代)", text, re.IGNORECASE))
    if any(not 1880 <= int(value) <= 2190 or int(value) % 10 for value in raw_decades):
        return values, text, "unsupported_filter"
    decades = raw_decades
    if len(decades) > 1:
        return values, text, "multiple_values"
    if decades:
        values["decade"] = int(next(iter(decades)))
        text = _replace(text, r"(?<!\d)(?:18|19|20|21)\d0(?:s\b|\s*年代)")
    if re.search(r"(?<!\d)\d0(?:s\b|\s*年代)|[一二三四五六七八九十零]+年代|\b(?:twenties|thirties|forties|fifties|sixties|seventies|eighties|nineties)\b", text, re.IGNORECASE):
        return values, text, "ambiguous_request"
    # Protect literal English names (e.g. Jordan Peele) from country/genre words.
    english_people = list(re.finditer(r"\b(directed by|starring|by|with)\s+(.+?)(?=\s+(?:from|in|released|sorted|sort|and)\b|[,.!?]|$)", text, re.IGNORECASE))
    if len(english_people) > 1 or english_people and "person" in values:
        return values, text, "multiple_values"
    if english_people:
        match = english_people[0]
        name = match.group(2).strip()
        if not name or len(name) > 100:
            return values, text, "ambiguous_request"
        role = match.group(1).lower()
        values.update(person=name, person_role="director" if role in ("by", "directed by") else "actor" if role == "starring" else "any")
        text = text[:match.start()] + " " + text[match.end():]
    countries = {**vocabulary.country_aliases, **_COUNTRY_WORDS}
    text, found = _aliases(text, countries)
    if len(found) > 1:
        return values, text, "multiple_values"
    if found:
        values["country"] = next(iter(found))
    genres = {alias: genre.canonical_name for alias, genre in vocabulary.genre_aliases.items()}
    text, found = _aliases(text, genres)
    if len(found) > 1:
        return values, text, "multiple_values"
    if found:
        values["genre"] = next(iter(found))
    return values, text, None


def remaining(text):
    return re.sub(r"[\s.,!?，。！？、:：;；\-–—'’\"]", "", _replace(text, _FILLERS))


def grounded(plan, question, *, edited=False):
    known, text, reason = local_plan(question)
    if reason:
        return False
    # Only the explicit local edit API can set this; model schemas cannot. The
    # original input remains visible as context and the UI says 'Adjusted'.
    if edited:
        return True
    for field, value in known.items():
        actual = getattr(plan, field)
        if field == "country":
            actual = vocabulary.resolve_country(actual)
        elif field == "genre":
            resolved = vocabulary.resolve_genre(actual)
            actual = resolved.canonical_name if resolved else None
        if actual != value:
            return False
    # AI may identify a literal name without an explicit 'by/with' phrase. It
    # still has to occur in the question and resolve against local identities.
    if plan.person and "person" not in known:
        pattern = _term_pattern(plan.person)
        if not re.search(pattern, question, re.IGNORECASE) or plan.person_role != "any":
            return False
        text = _replace(text, pattern)
    for field in ("genre", "country", "decade", "view", "sort", "direction"):
        if field not in known and getattr(plan, field) != getattr(AskPlan(), field):
            return False
    return not remaining(text)


class DiscoverySearchService:
    def __init__(self, *, ask=None):
        self.ask = ask or ask_service

    @staticmethod
    def state(status, reason=None, *, source="local"):
        return {"version": "discovery.v1", "status": status, "source": source, "reason": reason,
                "plan": None, "person_id": None, "constraints": [], "issues": [], "results": None}

    def interpret(self, request: DiscoveryQuestion):
        question = request.question
        if has_private_input(question):
            raise AskError("ask_private_input", 422)
        from app.services.search_local import LocalSearch
        literal = LocalSearch(ask_module.engine).literal_request(question)
        if literal is not None:
            return literal
        # A known literal title wins even if it contains condition words or years.
        term = keyword_text(question)
        if len(term) <= 200:
            with Session(ask_module.engine) as session:
                exact = session.exec(select(FilmSearchReadModel.film_id).join(LibraryFilmReadModel,
                    FilmSearchReadModel.film_id == LibraryFilmReadModel.film_id).where(
                    LibraryFilmReadModel.visible.is_(True), FilmSearchReadModel.exact_titles.contains(
                        "\n" + normalize_metadata_text(term) + "\n", autoescape=True)).limit(1)).first()
                exact_person = ask_module.AskService._people(session, term, exact_only=True)[1] if not exact else False
            if exact or exact_person:
                return self.state("keyword")
        if is_extended_request(question):
            plan, leftover, issue = parse_extended(question)
            if issue or leftover or plan is None:
                return self.state("clarify" if issue == "ambiguous_request" else "unsupported",
                    issue or "incomplete_request")
            return search_plan_executor.resolve(plan)
        values, text, issue = local_plan(question)
        conditional = bool(re.search(_REQUEST, keyword_text(question), re.IGNORECASE) or "view" in values or "person" in values)
        if not conditional:
            return self.state("keyword") if len(question) <= 200 else self.state("clarify", "long_keywords")
        reason = unsupported_reason(question) or issue
        if reason:
            return self.state("clarify" if reason == "ambiguous_request" else "unsupported", reason)
        if not remaining(text):
            return self._resolve(AskPlan(**values), source="local")
        # A bare title/name, even prefixed with 'find', remains ordinary search.
        if not values:
            if not re.search(r"\b(?:that|which|under|over|between|short|long|good|something)\b|一点|比较|一部|什么|适合", question, re.IGNORECASE):
                return self.state("keyword") if len(question) <= 200 else self.state("clarify", "long_keywords")
        if not request.allow_ai:
            return self.state("needs_ai" if self.ask.interpreter.configured() else "unavailable", "submit_to_interpret" if self.ask.interpreter.configured() else "ask_not_configured")
        try:
            interpreted = self.ask.interpreter.interpret_search(request)
        except AskError as exc:
            if exc.code == "ask_private_input":
                raise
            return self.state("unavailable", exc.code)
        if interpreted.status != "ready":
            return self.state(interpreted.status, "incomplete_request", source="ai")
        if interpreted.confidence < .9 or interpreted.unhandled:
            return self.state("clarify", "incomplete_request", source="ai")
        if not grounded(interpreted.plan, question):
            return self.state("unsupported", "incomplete_request", source="ai")
        return self._resolve(interpreted.plan, source="ai")

    def _resolve(self, plan, *, source, person_id=None):
        resolved = self.ask.resolve(AskResolveRequest(plan=plan, person_id=person_id))
        return {**self.state(resolved["status"], source=source), **resolved, "version": "discovery.v1"}

    def query(self, request: DiscoveryQuery):
        if has_private_input(request.question):
            raise AskError("ask_private_input", 422)
        if isinstance(request.plan, SearchPlan):
            from app.services.search_local import LocalSearch
            literal = LocalSearch(ask_module.engine).literal_binding(request.question)
            # Re-validate the complete original identity request even for edits.
            # Explicit chip/sort changes may alter its plan, never excuse an
            # unsupported qualifier or an unresolved original identity.
            bound = (literal is not None and not literal.issue and literal.plan is not None
                     and (request.edited or literal.plan == request.plan))
            if not bound and not grounded_extended(request.plan, request.question, edited=request.edited):
                return self.state("unsupported", "incomplete_request")
            if request.person_id:
                raise AskError("ask_invalid_selection", 422)
            return search_plan_executor.query(request.plan, people_ids=request.people_ids, offset=request.offset)
        if request.people_ids:
            raise AskError("ask_invalid_selection", 422)
        reason = unsupported_reason(request.question)
        if reason or not grounded(request.plan, request.question, edited=request.edited):
            return self.state("unsupported", reason or "incomplete_request")
        result = self.ask.query(AskQueryRequest(plan=request.plan, person_id=request.person_id,
            confirmed=True, offset=request.offset), limit=40)
        return {**self.state(result["status"]), **result, "version": "discovery.v1"}


discovery_search_service = DiscoverySearchService()
