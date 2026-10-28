"""Bounded clause helpers: normalization is for parsing, never model rewriting.

Only complete control/hard clauses are consumed. Story/preference text survives
verbatim in the semantic query. Unknown requirements remain errors.
"""
import re

from app.contracts.bound_search_plan import SearchPlan
from app.services.search_literals import hard_plan

_YEAR = r"(?:18|19|20)\d{2}|2100"
_PART = re.compile(r"[,;:。；：]|(?<=[.!?])\s+")
_QUOTED = re.compile(r'''《[^》]+》|“[^”]+”|"[^"]+"|'[^']+' ''', re.X)
_LOCAL = re.compile(
    r"(?:(?:只|就)?(?:在|查|找|搜索)?(?:这套|这个|本地|本)?(?:资料库|片库|库)(?:里|中)?(?:查找|找|查询|搜索)?|"
    r"(?:只|就)查(?:这套|这个|本地)?(?:资料库|片库|库)|"
    r"(?:如果)?没有(?:匹配)?(?:就)?(?:请)?(?:直接)?(?:说没有|返回空结果|不要推荐|不用推荐|不要凑数)|"
    r"(?:(?:这套|这个|本地)(?:资料库|片库|库)(?:里|中)?)?没有(?:匹配)?(?:就)?(?:不要|不用)(?:拿)?(?:其他|其它|新|旧)?片(?:推荐|凑)|"
    r"没有(?:匹配)?(?:就)?(?:不要|不用)推荐(?:其他|其它|新|旧)?片|"
    r"(?:search|look|find) (?:only )?in (?:this|the local) (?:library|collection)|"
    r"(?:no|without) (?:substitutes|relaxation)|(?:if none|no matches?)[ ,]*(?:return nothing|say so))", re.I)
_PREFERENCE = re.compile(
    r"(?:^|[,;。])\s*(?:(?:但|也|并|而)?(?:不要求|不追求|不一定(?:要)?|不必|不限于|不只(?:是)?|不是(?:只要|只|单纯))|"
    r"(?:but )?(?:not (?:necessarily|merely|simply|just|only)|(?:i )?don['’]t (?:need|require)))"
    r"(?:(?!(?:但是|并且|而且|但|且)(?:必须|只能|只要|不得|一定要)|\b(?:and|but|also|however)\s+(?:must|only)\b)[^,;。])*(?=$|[,;。]|(?:但是|并且|而且|但|且)(?:必须|只能|只要|不得|一定要)|\b(?:and|but|also|however)\s+(?:must|only)\b)", re.I)
_CONTENT = re.compile(r"\b(?:plot|story|theme|mood|about|stories)\b|想看|想找|找的是|故事|剧情|重点|讲述|探讨|感觉|记忆|感知|(?:一个|有一部|有部).{4}", re.I)
_CONTRAST_EN = re.compile(r"\b(?:not|isn['’]t)(?=\s+the\s+(?:one|film|movie)\s+(?:where|in which)\b)", re.I)
_CONTRAST = re.compile(r"(?:不是|并非)(?=[^,;。]+)")
_STABLE = re.compile(r"(年份|条件)(?:都)?(?:不能|不得|不要)(?:放宽|更改)|不要换(导演|演员)凑数")


def parts(text):
    protected = [m.span() for m in _QUOTED.finditer(text)]
    end = 0
    for match in _PART.finditer(text):
        if any(left <= match.start() < right for left, right in protected):
            continue
        yield text[end:match.start()].strip()
        end = match.end()
    yield text[end:].strip()


def guard_text(text, context=None):
    # Soft preference scope stops at a new mandatory clause. The original text
    # is retained for retrieval/rerank; this string is only a guard input.
    value = _PREFERENCE.sub(" ", text)
    if _CONTENT.search(context or text):
        def contrast(match):
            tail = re.split(r"[,;。]", value[match.start():], maxsplit=1)[0]
            plan, _ = hard_plan(tail, allow_languages=True)
            if plan is not None and plan != SearchPlan(version="search-plan.v2"):
                return match[0]
            # A story cue outside this clause proves nothing about its negation.
            # Only a closed referential plot contrast may bypass this guard.
            # Role/facet/source facts or quoted identities still need strict
            # binding, even when the clause ends with "that film".
            if (re.search(r"的(?:那|这)(?:一)?部$", tail)
                    and not _QUOTED.search(tail)
                    and not re.search(r"来自|制作|出品|国家|语言|类型|题材|导演|执导|主演|出演|配音|年份|上映|片长|评分|分钟", tail)):
                return " "
            return match[0]
        value = _CONTRAST.sub(contrast, value)
        value = _CONTRAST_EN.sub(" ", value)
    return value


def normalize_hard(text):
    value = text.strip(" ,;，；")
    for _ in range(3):
        value = re.sub(r"^(?:但是|但|并且|而且|也)(?=只要|必须|只找|不要|排除|不含|由|(?:电影|上映|发行)?年份|\d{4})", "", value)
        value = re.sub(r"^(?:只要|必须(?:是|为)?|只找)\s*", "", value)
    value = re.sub(r"^(?:(?:电影|影片|上映|发行)?年份|上映时间)\s*(?:必须)?(?:是|为|在)?\s*", "", value)
    value = value.replace("—", "-").replace("–", "-")
    value = re.sub(r"(\d{4})\s+年", r"\1年", value)
    value = re.sub(r"(导演|执导|主演|出演)的(?:另一部|其他|其它)(?:电影|影片)?$", r"\1的电影", value)
    value = re.sub(rf"({_YEAR})\s*年?\s*(?:或更早|及以前|及之前)(?:的)?$", r"through \1", value)
    value = re.sub(rf"({_YEAR})\s*年?\s*(?:或更晚|及以后|及之后)(?:的)?$", r"since \1", value)
    return value.strip()


def _hard_clause(text, plan):
    if plan is None or plan == SearchPlan(version="search-plan.v2"):
        return False
    # A protected story noun can coincide with a genre/country label. Only a
    # framed facet clause is metadata; e.g. "a family" is not Family genre.
    fields = plan.model_dump()
    facet_only = not any(fields.get(key) for key in
        ("people", "languages", "film_ids", "exclude_film_ids", "exclude_genres", "exclude_countries",
         "year_min", "year_max", "duration_min", "duration_max")) and plan.view == "all" and plan.sort == "title"
    return not facet_only or bool(re.search(r"\b(?:films?|movies?|genre|country)\b|电影|影片|片子|类型|国家|地区", text, re.I))


def constraint_plan(text, lookup, *, extra_stable=()):
    hard, stable = [], list(extra_stable)
    for part in parts(text):
        normalized = normalize_hard(part)
        control = normalized.rstrip(" .!?！？")
        if not control or _LOCAL.fullmatch(control):
            continue
        match = _STABLE.fullmatch(control)
        if match:
            stable.append(next(value for value in match.groups() if value))
            continue
        original, issue = hard_plan(part, lookup, allow_languages=True)
        hard.append(part if original is not None and not issue else normalized)
    bound, issue = hard_plan(" ; ".join(hard), lookup, allow_languages=True)
    if issue or bound is None:
        return bound, issue
    for kind in stable:
        proven = ((kind == "年份" and (bound.year_min is not None or bound.year_max is not None))
            or (kind == "条件" and bound != SearchPlan(version="search-plan.v2"))
            or (kind in ("导演", "演员") and any(not p.exclude and p.role in
                ("any", "director" if kind == "导演" else "actor") for p in bound.people)))
        if not proven:
            return None, "incomplete_request"
    return bound, None


def partition(text, lookup, guard, *, hard_context=""):
    """Return hard fragments and content only after proving a clause boundary."""
    hard, content, stable, controls = [], [], [], False
    for part in parts(text):
        part = part.strip()
        if not part:
            continue
        if _LOCAL.fullmatch(part.rstrip(" .!?！？")):
            controls = True
            continue
        match = _STABLE.fullmatch(part.rstrip(" .!?！？"))
        if match:
            stable.append(next(value for value in match.groups() if value))
            continue
        plan, issue = hard_plan(part, lookup, allow_languages=True)
        normalized = part if plan is not None and not issue else normalize_hard(part)
        plan, _ = hard_plan(normalized, lookup, allow_languages=True)
        if _hard_clause(normalized, plan):
            hard.append(normalized)
            continue
        issue = guard(part, context=text)
        if issue:
            return None, None, issue
        content.append(part)
    if stable:
        _, issue = constraint_plan(hard_context + " ; " + " ; ".join(hard), lookup, extra_stable=stable)
        if issue:
            return None, None, issue
    if not hard and not controls and not stable:
        return None
    if not content or all(re.fullmatch(r"please|thanks", part, re.I) for part in content):
        return None  # Pure factual requests retain the ordinary SQL grammar.
    return " ; ".join(hard), ", ".join(content), None


def reference_tail(text, reference):
    """Consume self-exclusion only: reference IDs are independently excluded."""
    remaining = []
    original = list(parts(text))
    for part in original:
        value = part.strip(" .!?！？")
        if re.fullmatch(r"(?:也|但)?(?:不要|别返回|不返回)(?:这部|那部)?(?:原片|原电影|原影片)|原片不要|"
                        r"(?:but )?(?:not|excluding) (?:the )?(?:original(?: film)?|film itself|movie itself|this film)", value, re.I):
            continue
        match = re.fullmatch(r"(?:也|但)?(?:不要|别返回|不返回)\s*(.+?)(?:本身|这部原片)|(?:not|excluding)\s+(.+?)\s+itself", value, re.I)
        if match and next(x for x in match.groups() if x).strip(" 《》\"'").casefold() == reference.casefold():
            continue
        remaining.append(part)
    return text if len(original) == len(remaining) else ", ".join(remaining)
